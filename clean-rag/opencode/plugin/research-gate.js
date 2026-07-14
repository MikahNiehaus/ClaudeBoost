// clean-rag research gate for OpenCode.
//
// Mirrors clean-rag/hooks/research-gate.py plus research_state.py: a code edit is
// blocked until research has actually covered THAT FILE this session. "Covered"
// means one of two things:
//
//   1. An agent (research-agent or triage-agent) or any tool emitted a
//      "COVERS: a, b, c" line naming the file (or a glob that matches it). This is
//      the same protocol the Python gate uses. See extractCoveredFiles below.
//   2. A rag_search ran this session AND came back with a non zero result. A non
//      zero rag_search is treated as project wide research: it lets any code file
//      in the session through. A zero result rag_search does NOT count, because an
//      empty search proves nothing was found and must not unlock edits.
//
// Precedence, checked in tool.execute.before:
//   named COVERS scope  >  session wide rag_search allow  >  block.
// A COVERS line covers exactly the files it names. A non zero rag_search covers the
// whole session. Nothing else opens the gate.
//
// Markdown and other non code files pass straight through, same as the Python gate.
// So do the usual scratch and metadata directories.
//
// KNOWN LIMITATION (sst/opencode issue #5894): tool.execute.before does not
// reliably intercept tool calls made by subagents, only by the primary agent.
// That means this gate is enforced for the primary agent's edits, but a subagent
// can currently slip a code edit through unblocked. This is an OpenCode bug, not
// something the plugin can fix from here. It is documented honestly rather than
// hidden. When #5894 is fixed the gate covers subagents too with no change here.
//
// SECOND HARD LIMIT: OpenCode has no message injection API (PR #19519 closed
// unmerged). Claude Code's passive verify after edit nudge is impossible here. The
// only model visible text a plugin can produce is a thrown error in
// tool.execute.before. So the "verify by running a test" reminder cannot be a
// passive note. It rides along on the next block message instead. See the
// untestedCode tracking below. This is a workaround for the missing injection API,
// not a real equivalent.
//
// The markers are in memory: Maps and Sets keyed by session id. The plugin module
// loads once per OpenCode process and lives for its lifetime, so state persists
// across tool calls within a session and resets when the process ends. That matches
// "this session". No file to write, nothing to clean up.
// ponytail: in memory markers, per process. If you need them to survive an OpenCode
// restart mid task, back them with a file under clean-rag/state/research/.

// Only these get gated. Everything else, including .md, .json, .yaml, and configs,
// passes. Mirrors CODE_EXTENSIONS in research-gate.py.
const CODE_EXTENSIONS = new Set([
  ".py", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs",
  ".java", ".cs", ".go", ".rs", ".rb", ".php", ".swift", ".kt", ".scala",
  ".c", ".h", ".cpp", ".hpp", ".cc", ".m", ".mm",
  ".sh", ".bash", ".ps1", ".sql", ".vue", ".svelte",
]);

// Matched as whole path segments, not substrings. Mirrors EXEMPT_SEGMENTS.
const EXEMPT_SEGMENTS = new Set([
  "workspace", "state", "plans", "docs", "node_modules",
  ".claude", ".claudeboost", ".git", "__pycache__", "scratchpad",
]);

// Append only log so you can watch the gate work: what it blocked, what it let
// through, and when research was recorded. Lives next to the OpenCode config.
// Tail it: the file is clean-rag-gate.log in ~/.config/opencode (or
// $XDG_CONFIG_HOME/opencode). Logging never throws, a broken log must not break
// the gate.
import { appendFileSync, existsSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";

function logPath() {
  const base = process.env.XDG_CONFIG_HOME
    ? process.env.XDG_CONFIG_HOME
    : join(homedir(), ".config");
  return join(base, "opencode", "clean-rag-gate.log");
}

function gateLog(event, detail) {
  const line = `${new Date().toISOString()}  ${event}  ${JSON.stringify(detail)}\n`;
  try {
    appendFileSync(logPath(), line);
  } catch (_) {
    // fall back to stderr, which OpenCode captures, but never throw
    try { process.stderr.write("[clean-rag-gate] " + line); } catch (_) {}
  }
}

function isCodeFile(filePath) {
  if (!filePath) return false;
  const norm = String(filePath).replace(/\\/g, "/");
  const parts = norm.split("/").filter(Boolean);

  const name = parts[parts.length - 1] || "";
  const dot = name.lastIndexOf(".");
  const ext = dot >= 0 ? name.slice(dot).toLowerCase() : "";
  if (!CODE_EXTENSIONS.has(ext)) return false;

  for (const seg of parts) {
    if (EXEMPT_SEGMENTS.has(seg.toLowerCase())) return false;
  }
  return true;
}

// A file that looks like a test. Used only for the verify by running reminder,
// never for gating: a test file is still a code file and still needs research.
function isTestFile(filePath) {
  if (!filePath) return false;
  const name = String(filePath).replace(/\\/g, "/").split("/").pop().toLowerCase();
  return name.startsWith("test_")
    || name.includes(".test.")
    || name.includes(".spec.")
    || name.includes("_test.");
}

// Does a shell command look like it runs tests? Best effort, for the reminder.
function isTestCommand(cmd) {
  if (!cmd) return false;
  const s = String(cmd);
  return /\b(vitest|jest|pytest|mocha|ava|jasmine)\b/i.test(s)
    || /\bnpm\s+(run\s+)?test\b/i.test(s)
    || /\b(yarn|pnpm)\s+test\b/i.test(s)
    || /\bnode\s+--test\b/i.test(s)
    || /\bplaywright\s+test\b/i.test(s);
}

// Port of research_state.py extract_covered_files. An agent declares scope with a
// line like:  COVERS: clean-rag/server/app.py, clean-rag/hooks/*.py
// Split on comma, trim, strip surrounding backticks. No COVERS line means nothing
// is covered, which is deliberate: an agent that cannot say what it looked at gives
// the gate nothing to check.
function extractCoveredFiles(text) {
  if (!text) return [];
  for (const line of String(text).split(/\r?\n/)) {
    const stripped = line.trim().replace(/^[*#\s]+/, "").trim();
    if (stripped.toUpperCase().startsWith("COVERS:")) {
      const raw = stripped.slice(stripped.indexOf(":") + 1);
      return raw
        .split(",")
        .map((p) => p.trim().replace(/^`+|`+$/g, "").trim())
        .filter(Boolean);
    }
  }
  return [];
}

function normalize(p) {
  return String(p).replace(/\\/g, "/").toLowerCase();
}

function escapeRegex(s) {
  return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

// Port of research_state.py file_in_scope. Exact path suffix match plus glob
// support: * stays within a directory, ** crosses separators.
function fileInScope(filePath, covered) {
  const norm = normalize(filePath);

  for (let entry of covered) {
    entry = entry.trim().replace(/^[/\\]+|[/\\]+$/g, "");
    entry = normalize(entry);
    if (!entry) continue;

    if (entry.includes("*")) {
      let pattern = escapeRegex(entry)
        .replace(/\\\*\\\*/g, "\x00") // ** placeholder
        .replace(/\\\*/g, "[^/]*");    // single * stays in one segment
      pattern = pattern.replace(/\x00/g, ".*");
      if (new RegExp(pattern + "$").test(norm)) return true;
      continue;
    }

    if (norm === entry || norm.endsWith("/" + entry)) return true;
  }
  return false;
}

// A rag_search only counts as research if it actually found something. The MCP
// server returns {"results":[...], "total":N} as a JSON string. Zero results, an
// empty list, or an error must all read as "no research happened".
function ragHasResults(outputStr) {
  if (!outputStr) return false;
  try {
    const data = JSON.parse(outputStr);
    if (data && typeof data === "object") {
      if (data.error) return false;
      if (Array.isArray(data.results)) return data.results.length > 0;
      if (typeof data.total === "number") return data.total > 0;
    }
  } catch (_) {
    // Not JSON. Fall back to substring checks so a wrapped or truncated payload
    // still fails closed on the obvious empty shapes.
  }
  const s = String(outputStr);
  if (/"total"\s*:\s*0\b/.test(s)) return false;
  if (/"results"\s*:\s*\[\s*\]/.test(s)) return false;
  if (/"error"\s*:/.test(s)) return false;
  return s.trim().length > 0;
}

// A run_tests tool result counts as "tests passed this session" only when it
// actually passed. The MCP server returns {"has_tests":true,"passed":true,...} as
// a JSON string. Anything else (failed, no tests, an error, unparseable) reads as
// not passed, so the reminder keeps nudging.
function runTestsPassed(outputStr) {
  if (!outputStr) return false;
  try {
    const data = JSON.parse(outputStr);
    if (data && typeof data === "object") return data.passed === true;
  } catch (_) {
    // Not JSON. Fall back to a substring check so a wrapped payload still reads.
  }
  return /"passed"\s*:\s*true\b/.test(String(outputStr));
}

export const ResearchGate = async () => {
  // Files each session's research has named via COVERS lines.
  const coveredScopes = new Map(); // sessionID -> string[]
  // Sessions where a non zero rag_search ran. Grants a session wide allow.
  const ragProject = new Set(); // sessionID
  // Last code file written that has not been followed by a test. Best effort,
  // used only to append the verify by running reminder onto a block message.
  const untestedCode = new Map(); // sessionID -> filePath
  // Sessions where the run_tests tool came back passed=true. Best effort, so the
  // reminder can say "tests have not passed this session" only when true.
  const testsPassed = new Set(); // sessionID

  return {
    // After a tool runs, read its result text. Two things can happen:
    //   a) the text carries a COVERS line: record those file globs for the session.
    //   b) the tool was rag_search: mark the session researched only if the result
    //      was non zero.
    "tool.execute.after": async (input, result) => {
      const session = input && input.sessionID;
      const tool = (input && input.tool) || "";
      const text = result && typeof result.output === "string" ? result.output : "";

      const covers = extractCoveredFiles(text);
      if (covers.length) {
        const existing = coveredScopes.get(session) || [];
        coveredScopes.set(session, existing.concat(covers));
        gateLog("covers-recorded", { session, tool, covers });
      }

      if (tool.includes("rag_search")) {
        if (ragHasResults(text)) {
          ragProject.add(session);
          gateLog("rag-search-nonzero", { session, tool });
        } else {
          gateLog("rag-search-zero-ignored", { session, tool });
        }
      }

      // A non empty web search is real research too, and for a FRESH project it's
      // the ONLY research available: rag_search always returns 0 on an unindexed
      // project, so without this a new project could never satisfy the gate except
      // by a COVERS line, which a weak model rarely produces. A web search that
      // finds a real reference (grounding, the lever that lifts weak models) is
      // exactly what should unlock. Same session wide allow as a non zero rag_search.
      if (tool.includes("web_search") || tool.includes("web-search")) {
        if (ragHasResults(text)) {
          ragProject.add(session);
          gateLog("web-search-nonzero", { session, tool });
        } else {
          gateLog("web-search-zero-ignored", { session, tool });
        }
      }

      // run_tests coming back passed=true is the execution feedback signal. Mark
      // the session and clear the untested flag so the reminder stops nagging.
      if (tool.includes("run_tests")) {
        if (runTestsPassed(text)) {
          testsPassed.add(session);
          untestedCode.delete(session);
          gateLog("run-tests-passed", { session, tool });
        } else {
          gateLog("run-tests-not-passed", { session, tool });
        }
      }
    },

    // Before an edit or write, block a code file unless it is in a covered scope
    // or a non zero rag_search ran this session.
    "tool.execute.before": async (input, output) => {
      const session = input && input.sessionID;
      const tool = input && input.tool;

      const args = (output && output.args) || {};
      const filePath = args.filePath || args.path || args.file || "";
      const command = args.command || args.cmd || "";

      // Verify by running reminder, tracking side. Clear the untested flag when a
      // test file is written or a test command runs. Done on intent (before the
      // tool executes) because that is where args are reliably available. Best
      // effort, and clearly a workaround for OpenCode's missing injection API.
      if (tool === "bash" && isTestCommand(command)) untestedCode.delete(session);
      if ((tool === "edit" || tool === "write") && isTestFile(filePath)) untestedCode.delete(session);

      if (tool !== "edit" && tool !== "write") return;

      if (!isCodeFile(filePath)) {
        gateLog("allowed", { session, tool, file: filePath, why: "not a gated code file" });
        return;
      }

      const scopes = coveredScopes.get(session) || [];
      if (fileInScope(filePath, scopes)) {
        gateLog("allowed-in-scope", { session, tool, file: filePath, covers: scopes });
        if (!isTestFile(filePath)) untestedCode.set(session, filePath);
        return;
      }
      if (ragProject.has(session)) {
        gateLog("allowed-in-scope", { session, tool, file: filePath, why: "non zero rag_search this session (project wide allow)" });
        if (!isTestFile(filePath)) untestedCode.set(session, filePath);
        return;
      }

      // Creating a NEW file (does not exist yet) is different from editing an
      // existing one. You cannot per-file-cover a file that does not exist, so the
      // research-agent guessing its exact path is brittle: it predicts a nested
      // layout, the builder writes a flat one, and every new file blocks. So for a
      // file that is not on disk yet, a real research-agent run this session (it
      // emitted at least one COVERS line, tracked in coveredScopes) is enough.
      // Editing an EXISTING file still needs the strict per-file COVERS match above.
      // A missing file check can race a concurrent write, but the worst case is a
      // just-created file being treated as new, which is harmless here.
      let fileExists = true;
      try { fileExists = existsSync(filePath); } catch (_) { fileExists = true; }
      const researchedThisSession = (coveredScopes.get(session) || []).length > 0;
      if (!fileExists && researchedThisSession) {
        gateLog("allowed-new-file-research-done", { session, tool, file: filePath });
        if (!isTestFile(filePath)) untestedCode.set(session, filePath);
        return;
      }

      // Block. Name what research covered versus the file being edited, same as the
      // Python gate's "research covered X, not this file" message.
      const covered = Array.from(new Set(scopes)).sort();
      let scopeMsg;
      if (covered.length) {
        const shown = covered.slice(0, 4).join(", ") + (covered.length > 4 ? " ..." : "");
        scopeMsg = "Research this session covered " + shown + ", not " + filePath + ".";
      } else {
        scopeMsg = "No research has covered any file this session.";
      }

      const pending = untestedCode.get(session);
      const testReminder = pending && !testsPassed.has(session)
        ? "\n\nAlso: you wrote " + pending + " and run_tests has not passed this "
          + "session. Call the run_tests tool on what you wrote, then fix from the "
          + "real failure output."
        : "";

      gateLog("blocked-not-in-scope", { session, tool, file: filePath, covered, untested: pending || null });
      throw new Error(
        "BLOCKED by clean-rag research gate: this file is not in a researched scope.\n\n" +
        "About to edit: " + filePath + "\n" +
        scopeMsg + "\n\n" +
        "To proceed, then retry the edit:\n" +
        "  1. BEST for a fresh project: spawn research-agent. It does the web " +
        "search itself, once, ranks the sources, and emits a COVERS: line naming " +
        "the files it researched. That unlocks the gate. This is the reliable path.\n" +
        "  2. rag_search about this file also works IF the project is indexed. On a " +
        "fresh project it returns 0 and will NOT unlock the gate.\n" +
        "  3. You MAY call web_search_fallback ONCE as a quick check. If it comes " +
        "back empty, do NOT call it again, the scraper rate limits rapid repeats. " +
        "Spawn research-agent instead. Never loop web_search_fallback.\n\n" +
        "Markdown and config files are never gated." + testReminder
      );
    },
  };
};
