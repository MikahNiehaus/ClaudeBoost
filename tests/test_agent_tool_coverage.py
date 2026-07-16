"""
Adversarial test: every tool name mentioned in the "Use the real tools" prose
sections of bad-cop.md and good-cop.md must appear in that file's frontmatter
tools: line.

Also checks:
- cross-file alignment of the new sections
- .NET 10 warning language vs. the authoritative source (debug-agent.xml line 68)
- close_debug_session appears in the lifecycle (session must be closed)
- good-cop .NET fallback does not contradict good-cop's fix mandate
"""

import re
import sys

BAD_COP  = r"C:\Development\ClaudeBoost\clean-rag\portable\agents\bad-cop.md"
GOOD_COP = r"C:\Development\ClaudeBoost\clean-rag\portable\agents\good-cop.md"
DEBUG_XML = r"C:\Development\ClaudeBoost\agents\debug-agent.xml"

# ── helpers ──────────────────────────────────────────────────────────────────

def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()

def parse_frontmatter_tools(text):
    """Return set of tool names from the 'tools:' frontmatter line."""
    for line in text.splitlines():
        if line.startswith("tools:"):
            raw = line[len("tools:"):].strip()
            return set(t.strip() for t in raw.split(","))
    return set()

def extract_section(text, heading):
    """Return the text of a ## section by its heading, or empty string."""
    pattern = rf"^## {re.escape(heading)}\s*$"
    lines = text.splitlines()
    in_section = False
    collected = []
    for line in lines:
        if re.match(pattern, line):
            in_section = True
            continue
        if in_section:
            if line.startswith("## "):
                break
            collected.append(line)
    return "\n".join(collected)

def find_tool_refs_in_prose(prose):
    """
    Extract tool name references from prose. Two forms:
      - backtick-quoted: `create_debug_session`
      - mcp__ prefixed: mcp__playwright__browser_snapshot (no backtick needed)
    Returns set of bare tool names (no mcp__ prefix) and full mcp__ names.
    """
    # backtick-quoted identifiers
    backtick = set(re.findall(r"`([a-zA-Z_][a-zA-Z0-9_]*)`", prose))
    # mcp__ identifiers (may appear without backticks)
    mcp_full = set(re.findall(r"mcp__[a-zA-Z0-9_]+", prose))
    return backtick, mcp_full

FAILURES = []
PASSES   = []

def check(label, condition, detail=""):
    if condition:
        PASSES.append(f"PASS  {label}")
    else:
        FAILURES.append(f"FAIL  {label}" + (f"\n      {detail}" if detail else ""))

# ── load files ────────────────────────────────────────────────────────────────

bad_text  = read(BAD_COP)
good_text = read(GOOD_COP)
xml_text  = read(DEBUG_XML)

bad_tools  = parse_frontmatter_tools(bad_text)
good_tools = parse_frontmatter_tools(good_text)

bad_section  = extract_section(bad_text,  "Use the real tools, not print statements")
good_section = extract_section(good_text, "Use the real tools to confirm the fix")

# ── 1. Section actually present ───────────────────────────────────────────────

check("bad-cop: 'Use the real tools' section present",
      bool(bad_section.strip()),
      "Section not found")

check("good-cop: 'Use the real tools to confirm the fix' section present",
      bool(good_section.strip()),
      "Section not found")

# ── 2. Tool names in prose → must be in frontmatter ──────────────────────────

# Bare function names that map to mcp-debugger tools
DEBUGGER_BARE = {
    "create_debug_session", "set_breakpoint", "continue_execution",
    "get_variables", "close_debug_session", "step_over", "step_into",
    "step_out", "get_stack_trace", "evaluate_expression", "list_debug_sessions",
}
# Playwright bare names
PLAYWRIGHT_BARE = {
    "browser_navigate", "browser_click", "browser_type", "browser_fill_form",
    "browser_press_key", "browser_snapshot", "browser_take_screenshot",
    "browser_console_messages", "browser_network_requests", "browser_evaluate",
    "browser_wait_for", "browser_find", "browser_close",
}

def check_prose_tools_in_frontmatter(section_prose, frontmatter_tools, file_label):
    backtick_refs, mcp_refs = find_tool_refs_in_prose(section_prose)

    # Check bare debugger function names mentioned in backticks
    for bare in DEBUGGER_BARE:
        if bare in backtick_refs:
            full = f"mcp__mcp-debugger__{bare}"
            check(
                f"{file_label}: `{bare}` mentioned in prose → '{full}' in frontmatter",
                full in frontmatter_tools,
                f"Tool '{full}' NOT in frontmatter tools list"
            )

    # Check bare playwright names mentioned in backticks
    for bare in PLAYWRIGHT_BARE:
        if bare in backtick_refs:
            full = f"mcp__playwright__{bare}"
            check(
                f"{file_label}: `{bare}` mentioned in prose → '{full}' in frontmatter",
                full in frontmatter_tools,
                f"Tool '{full}' NOT in frontmatter tools list"
            )

    # Check mcp__ prefixed names found directly in prose
    # Filter out bare prefix stubs like 'mcp__playwright__' (no function suffix)
    # — these appear as glob patterns (mcp__playwright__*) not real tool refs.
    for mcp_name in mcp_refs:
        if mcp_name.endswith("__"):
            # glob stub, not a real tool reference — skip
            continue
        check(
            f"{file_label}: '{mcp_name}' mentioned in prose → in frontmatter",
            mcp_name in frontmatter_tools,
            f"Tool '{mcp_name}' NOT in frontmatter tools list"
        )

check_prose_tools_in_frontmatter(bad_section,  bad_tools,  "bad-cop")
check_prose_tools_in_frontmatter(good_section, good_tools, "good-cop")

# ── 3. Lifecycle completeness: close_debug_session must appear ────────────────

check("bad-cop: close_debug_session in lifecycle prose",
      "close_debug_session" in bad_section,
      "Lifecycle does not end with close_debug_session")

check("good-cop: close_debug_session in lifecycle prose",
      "close_debug_session" in good_section,
      "Lifecycle does not end with close_debug_session")

# ── 4. Playwright sequence: snapshot before screenshot ────────────────────────

def snapshot_before_screenshot(section):
    snap_pos = section.find("browser_snapshot")
    shot_pos = section.find("browser_take_screenshot")
    if snap_pos == -1 or shot_pos == -1:
        return False
    return snap_pos < shot_pos

check("bad-cop: browser_snapshot appears before browser_take_screenshot in prose",
      snapshot_before_screenshot(bad_section),
      "Order wrong or one/both missing")

check("good-cop: browser_snapshot appears before browser_take_screenshot in prose",
      snapshot_before_screenshot(good_section),
      "Order wrong or one/both missing")

# ── 5. console check required ─────────────────────────────────────────────────

check("bad-cop: browser_console_messages mentioned",
      "browser_console_messages" in bad_section)

check("good-cop: browser_console_messages mentioned",
      "browser_console_messages" in good_section)

# ── 6. browser_close required ─────────────────────────────────────────────────

check("bad-cop: browser_close mentioned",
      "browser_close" in bad_section)

check("good-cop: browser_close mentioned",
      "browser_close" in good_section)

# ── 7. OAuth exception present ────────────────────────────────────────────────

check("bad-cop: OAuth exception stated",
      "OAuth" in bad_section)

check("good-cop: OAuth exception stated",
      "OAuth" in good_section)

# ── 8. .NET 10 warning language vs. authoritative source ─────────────────────

# debug-agent.xml line 68 (authoritative):
# "netcoredbg 3.1.3 (latest as of 2026-06) cannot debug .NET 10 processes on
#  Windows: initialize handshake succeeds but setBreakpoints crashes the target
#  process."
#
# bad-cop says (lines 62-65): "the handshake succeeds but `setBreakpoints`
#  crashes the target process"
# good-cop says (lines 54-55): similar, but omits the detail about what exactly
#  crashes. Check both contain the key facts.

KEY_FACTS = [
    ("netcoredbg 3.1.3", "version number"),
    ("net10.0",          ".csproj TargetFramework check"),
    ("setBreakpoints",   "exact failing DAP method"),
]

for fact, label in KEY_FACTS:
    check(f"bad-cop: .NET warning contains '{fact}' ({label})",
          fact in bad_section,
          f"Key fact '{fact}' absent from bad-cop .NET warning")

# good-cop intentionally shorter — verify the key decision trigger is present
for fact, label in [("netcoredbg 3.1.3", "version"), ("net10.0", "TargetFramework check")]:
    check(f"good-cop: .NET warning contains '{fact}' ({label})",
          fact in good_section,
          f"Key fact '{fact}' absent from good-cop .NET warning")

# good-cop omits "setBreakpoints" — is that a problem?
# The fallback is "verify through test output alone" which is coherent with
# good-cop's fix role. Record this as a deliberate observation, not a failure.
if "setBreakpoints" not in good_section:
    PASSES.append("NOTE  good-cop omits 'setBreakpoints' detail — acceptable per fixer role, "
                  "fallback is 'verify through test output alone'")

# ── 9. Cross-file: localhost constraint alignment ─────────────────────────────

LOCALHOST_TOKENS = ["localhost", "127.0.0.1", "0.0.0.0", "*.local", "*.test"]
for tok in LOCALHOST_TOKENS:
    check(f"bad-cop:  localhost token '{tok}' present", tok in bad_section)
    check(f"good-cop: localhost token '{tok}' present", tok in good_section)

# ── 10. No contradiction: good-cop fallback vs. fix mandate ───────────────────
# "skip attach and verify through test output alone" — this is additive
# (net10.0 exception to debugger use), not a general skip-the-fix instruction.
# Verify the fallback is scoped to the net10.0 case, not a blanket opt-out.

fallback_scoped = re.search(
    r"net10\.0[^.]*?skip attach",
    good_section, re.DOTALL
)
check("good-cop: net10.0 fallback is scoped (appears after net10.0 condition, not general)",
      fallback_scoped is not None,
      "Fallback wording may be read as a general opt-out rather than net10.0-scoped")

# ── 11. bad-cop does NOT stamp VERIFIED (that's good-cop's job on real finds) ─
# bad-cop's CLOSING section should say it stamps VERIFIED only when finding
# nothing. Check the prose says "only good-cop" stamps VERIFIED when there IS a
# finding.
check("bad-cop: VERIFIED stamped by bad-cop only when nothing found (prose gate check)",
      "You do not stamp the verifier" in bad_text or
      "only good-cop does that" in bad_text or
      "zero real findings" in bad_text.lower())

# ── report ────────────────────────────────────────────────────────────────────

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
print("\n" + "="*60)
print("ADVERSARIAL TEST: agent tool coverage")
print("="*60)
for p in PASSES:
    print(p)
if FAILURES:
    print()
    for f in FAILURES:
        print(f)

print()
print(f"Result: {len(PASSES)} passed, {len(FAILURES)} failed")
if FAILURES:
    sys.exit(1)
else:
    print("ALL CHECKS PASSED")
    sys.exit(0)
