// clean-rag research gate for OpenCode.
//
// Mirrors clean-rag/hooks/research-gate.py: a code edit is blocked until research
// has actually happened this session. Here "research happened" means the clean-rag
// rag_search MCP tool ran at least once. No rag_search, no edit to a code file.
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
// The marker is in memory: a Set of session ids that have called rag_search. The
// plugin module loads once per OpenCode process and lives for its lifetime, so the
// Set persists across tool calls within a session and resets when the process ends.
// That matches "this session". No file to write, nothing to clean up.
// ponytail: in-memory marker, per process. If you need it to survive an OpenCode
// restart mid task, back it with a file under clean-rag/state/research/.

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

export const ResearchGate = async () => {
  // Session ids that have run rag_search at least once this process.
  const researched = new Set();

  return {
    // After a tool runs, if it was a clean-rag rag_search, mark the session as
    // researched. Matching on substring so it works whatever prefix OpenCode gives
    // the MCP tool (e.g. "clean-rag_rag_search").
    "tool.execute.after": async (input) => {
      if (input && typeof input.tool === "string" && input.tool.includes("rag_search")) {
        researched.add(input.sessionID);
      }
    },

    // Before an edit or write, block it if the target is a code file and this
    // session has not researched yet.
    "tool.execute.before": async (input, output) => {
      const tool = input && input.tool;
      if (tool !== "edit" && tool !== "write") return;

      const args = (output && output.args) || {};
      const filePath = args.filePath || args.path || args.file || "";
      if (!isCodeFile(filePath)) return;

      if (researched.has(input.sessionID)) return;

      throw new Error(
        "BLOCKED by clean-rag research gate: no research has run this session.\n\n" +
        "About to edit: " + filePath + "\n\n" +
        "Every code edit has to be covered by research. Call the clean-rag " +
        "rag_search MCP tool first (or spawn the research agent, which uses it), " +
        "then retry the edit. A markdown or config file needs no research and is " +
        "never gated."
      );
    },
  };
};
