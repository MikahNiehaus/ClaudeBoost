"""
Test that SKILL.md frontmatter is valid and complete.
A valid Claude skill frontmatter requires: name, description, allowed-tools.
Run with: python plans/test_skill_frontmatter.py
"""

import sys
import re

passed = 0
failed = 0


def test(name, fn):
    global passed, failed
    try:
        fn()
        print(f"  PASS  {name}")
        passed += 1
    except AssertionError as e:
        print(f"  FAIL  {name}")
        print(f"        {e}")
        failed += 1


def assert_true(cond, msg):
    if not cond:
        raise AssertionError(msg)


SKILL_PATHS = [
    "C:/Development/ClaudeBoost/clean-rag/portable/skills/walkthrough/SKILL.md",
    "C:/Users/mniehaus/.claude/skills/walkthrough/SKILL.md",
]

COMMAND_PATH = "C:/Development/ClaudeBoost/.claude/commands/walkthrough.md"


def parse_frontmatter(path):
    with open(path, encoding="utf-8") as f:
        content = f.read()
    if not content.startswith("---"):
        return None, content
    end = content.index("\n---\n", 3)
    fm_text = content[4:end]
    body = content[end + 5:]
    fm = {}
    for line in fm_text.splitlines():
        if ": " in line:
            k, v = line.split(": ", 1)
            fm[k.strip()] = v.strip()
        elif ":" in line and not line.strip().startswith("#"):
            k = line.split(":")[0].strip()
            fm[k] = ""
    return fm, body


for skill_path in SKILL_PATHS:
    label = "portable" if "portable" in skill_path else "installed"

    def make_test(path, lbl):
        def t():
            fm, body = parse_frontmatter(path)
            assert_true(fm is not None, f"{lbl} SKILL.md has no frontmatter")
            assert_true("name" in fm, f"{lbl}: missing 'name' field")
            assert_true(fm["name"] == "walkthrough", f"{lbl}: name should be 'walkthrough', got: {fm['name']}")
            assert_true("description" in fm, f"{lbl}: missing 'description' field")
            assert_true(len(fm["description"]) > 20, f"{lbl}: description too short: {fm['description']}")
            assert_true("allowed-tools" in fm, f"{lbl}: missing 'allowed-tools' field")
            tools = fm["allowed-tools"].split(", ")
            assert_true("mcp__playwright__browser_evaluate" in tools,
                        f"{lbl}: allowed-tools missing browser_evaluate")
            assert_true("mcp__playwright__browser_take_screenshot" in tools,
                        f"{lbl}: allowed-tools missing browser_take_screenshot")
            assert_true("mcp__playwright__browser_navigate" in tools,
                        f"{lbl}: allowed-tools missing browser_navigate")
            assert_true("Write" in tools, f"{lbl}: allowed-tools missing Write")
        return t

    test(f"SKILL.md frontmatter valid ({label})", make_test(skill_path, label))


def test_command_frontmatter():
    fm, body = parse_frontmatter(COMMAND_PATH)
    assert_true(fm is not None, "command .md has no frontmatter")
    assert_true("description" in fm, "command .md missing 'description'")
    assert_true("allowed-tools" in fm, "command .md missing 'allowed-tools'")
    assert_true("argument-hint" in fm, "command .md missing 'argument-hint'")
    assert_true("<url>" in fm.get("argument-hint", ""),
                "argument-hint should mention <url>")
    assert_true("$ARGUMENTS" in body,
                "command body should reference $ARGUMENTS")
    assert_true("walkthrough skill" in body.lower() or "walkthrough" in body.lower(),
                "command body should reference the walkthrough skill")


test("Command .md frontmatter valid", test_command_frontmatter)


def test_command_loads_skill():
    with open(COMMAND_PATH, encoding="utf-8") as f:
        body = f.read()
    assert_true(
        "walkthrough skill" in body.lower() or "load the" in body.lower(),
        "command should instruct loading the walkthrough skill"
    )
    assert_true(
        "localhost" in body.lower(),
        "command should mention localhost URL requirement"
    )


test("Command .md instructs loading the skill", test_command_loads_skill)


def test_skill_phases_present():
    with open(SKILL_PATHS[0], encoding="utf-8") as f:
        content = f.read()
    assert_true("## Phase 0" in content, "SKILL.md should have Phase 0")
    assert_true("## Phase 1" in content, "SKILL.md should have Phase 1")
    assert_true("## Phase 2" in content, "SKILL.md should have Phase 2")
    assert_true("## Phase 3" in content, "SKILL.md should have Phase 3")
    assert_true("## Phase 4" in content, "SKILL.md should have Phase 4")


test("SKILL.md has all 4 phases (0 through 4)", test_skill_phases_present)


def test_skill_safety_section():
    with open(SKILL_PATHS[0], encoding="utf-8") as f:
        content = f.read()
    assert_true("## Safety" in content, "SKILL.md should have Safety section")
    assert_true("Localhost only" in content or "localhost" in content.lower(),
                "Safety section should mention localhost restriction")
    assert_true("Headed browser" in content or "headed" in content.lower(),
                "Safety section should mention headed browser")
    assert_true("Clean up" in content or "clean up" in content.lower(),
                "Safety section should mention cleanup")


test("SKILL.md has complete Safety section", test_skill_safety_section)


def test_skill_reinjection_rule():
    with open(SKILL_PATHS[0], encoding="utf-8") as f:
        content = f.read()
    assert_true(
        "re inject" in content.lower() or "re-inject" in content.lower() or "Re injection" in content,
        "SKILL.md should document re-injection rule after navigation"
    )
    assert_true(
        "page navigation" in content.lower() or "browser_navigate" in content,
        "SKILL.md should mention re-injection is needed after browser_navigate"
    )


test("SKILL.md documents re-injection rule after navigation", test_skill_reinjection_rule)


def test_screenshot_unique_paths():
    with open(SKILL_PATHS[0], encoding="utf-8") as f:
        content = f.read()
    assert_true(
        "step-{N}" in content or "step-1.png" in content,
        "SKILL.md should specify per-step unique screenshot paths"
    )
    assert_true(
        "{SLUG}/step-" in content or "step-{N}" in content,
        "SKILL.md should use SLUG subdirectory for screenshots"
    )


test("SKILL.md specifies unique screenshot paths per step", test_screenshot_unique_paths)


print()
print(f"Results: {passed} passed, {failed} failed")
if failed > 0:
    sys.exit(1)
