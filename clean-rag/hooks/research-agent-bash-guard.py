#!/usr/bin/env python
"""PreToolUse guard on Bash, scoped to research agents via their own frontmatter.

Research agents read untrusted content: web snippets, scraped pages, indexed
docs. Any of it can carry text engineered to look like an instruction. Text
filtering that content is leaky by nature, so this doesn't try. It removes the
capability instead: a research agent that cannot run an arbitrary command cannot
be made to do anything, no matter how convincing the injected text is.

The agent only needs Bash for one thing, POSTing to the local clean-rag server.
So that's all it gets. Everything else is refused.

See tldrsec/prompt-injection-defenses: lowest privilege across every entity that
contributed to the prompt. The web contributed to this one.

Exit codes: 0 allows, 2 blocks with the stderr message shown to the agent.
"""

import json
import re
import shlex
import sys

# The only host a research agent may talk to from a shell.
ALLOWED_HOST_RE = re.compile(r"^https?://(127\.0\.0\.1|localhost):\d+/", re.IGNORECASE)

# Commands that are read only and can't be turned into a write or an exfil path.
SAFE_COMMANDS = {"curl", "echo", "cat", "ls", "pwd", "grep", "rg", "head", "tail", "wc"}

# Shell metacharacters that chain a second command onto an allowed one.
# "curl localhost:8613/search; rm -rf /" must not read as a curl call.
CHAINING = re.compile(r"[;&|`]|\$\(|>>|>")


def _check_git_clone(parts: list, command: str) -> int:
    """Allow 'git clone https://...' with no dangerous flags.

    git's own flag surface is a documented arbitrary-command vector:
    CVE-2022-25900 (--upload-pack), GHSA-jcxm-m3jx-f287 (ext:: transport).
    --template and -c/--config let untrusted repo content override hooks.
    Blocking them here means swiper can clone real repos without opening
    the exec path that makes git clone dangerous.
    """
    if len(parts) < 2 or parts[1] != "clone":
        sub = parts[1] if len(parts) > 1 else "(none)"
        return _refuse(f"git subcommand {sub!r} is not allowed; only 'git clone https://...' is permitted")

    # Some git flags take their value as a separate token (e.g. '--depth 1').
    # That value does not start with '-', so a naive "not a flag" filter would
    # misread the bare '1' as a candidate URL and reject it. Consume each known
    # value taking flag together with the token that follows it, so only real
    # positional arguments (the URL) remain. This is general, not a '--depth'
    # special case, so the same class of bug won't reappear for another flag.
    VALUE_FLAGS = {
        "--depth", "--branch", "-b", "--origin", "-o", "--reference",
        "--reference-if-able", "--separate-git-dir", "--shallow-since",
        "--shallow-exclude", "--jobs", "-j", "--filter",
        "--upload-pack", "-u", "--template", "--config", "-c",
    }
    urls = []
    skip_next = False
    for part in parts[2:]:
        if skip_next:
            skip_next = False
            continue
        if part.startswith("-"):
            # A value taking flag in space form consumes the next token.
            if part in VALUE_FLAGS:
                skip_next = True
            continue
        urls.append(part)
    if not urls:
        return _refuse("git clone with no URL")
    for url in urls:
        if not url.startswith("https://"):
            return _refuse(
                f"git clone URL must start with https:// (blocks git://, ssh://, "
                f"local paths, and the ext:: transport vector): {url!r}"
            )

    DANGEROUS_FLAGS = {"--upload-pack", "--template", "--config", "-c"}
    for part in parts[2:]:
        if part.startswith("ext::"):
            return _refuse(f"git ext:: transport is a documented command-execution vector: {part!r}")
        flag = part.split("=", 1)[0]
        if flag in DANGEROUS_FLAGS:
            return _refuse(
                f"{part!r} is a documented git clone command-execution vector "
                "(CVE-2022-25900 / GHSA-jcxm-m3jx-f287) and is not allowed"
            )

    # Full history is never needed for a swipe: the whole clone gets deleted
    # after the needed files are copied out, so history is dead weight the
    # instant it lands. Shallow only, enforced here rather than left to the
    # agent to remember.
    if "--depth" not in parts and not any(p.startswith("--depth=") for p in parts):
        return _refuse(
            "git clone must be shallow: add '--depth 1'. A swipe clone is "
            "temporary and gets deleted after the needed files are copied "
            "out, so full history is never needed."
        )

    return 0


def _refuse(reason: str) -> int:
    print(
        f"BLOCKED for research agent: {reason}\n\n"
        "Research agents run with a shell that only reaches the local clean-rag "
        "server, because they read untrusted web content and a compromised one "
        "must not be able to act.\n\n"
        "Allowed: curl to http://127.0.0.1:<port>/... \n"
        "For anything else use Read, Grep, Glob, WebSearch, or WebFetch. "
        "You cannot write files, and you do not need to.",
        file=sys.stderr,
    )
    return 2


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read())
    except Exception:
        # Can't parse the payload, so can't establish the command is safe.
        # Fail closed. A research agent losing Bash is a nuisance; a research
        # agent running an unvetted command is the thing this exists to stop.
        return _refuse("could not parse the tool payload")

    if payload.get("tool_name") != "Bash":
        return 0

    command = (payload.get("tool_input", {}).get("command") or "").strip()
    if not command:
        return 0

    if CHAINING.search(command):
        return _refuse(f"shell chaining or redirection is not allowed: {command!r}")

    try:
        parts = shlex.split(command)
    except ValueError as e:
        return _refuse(f"could not parse the command ({e}): {command!r}")

    if not parts:
        return 0

    binary = parts[0].rsplit("/", 1)[-1].rsplit("\\", 1)[-1].lower()
    if binary.endswith(".exe"):
        binary = binary[:-4]

    # git clone https:// is the one git subcommand swiper legitimately needs
    # to steal whole repos. Routed before SAFE_COMMANDS so it doesn't fall
    # into the "not on the allowlist" refuse path.
    if binary == "git":
        return _check_git_clone(parts, command)

    if binary not in SAFE_COMMANDS:
        return _refuse(f"{binary!r} is not on the allowlist")

    # curl is the one that can reach the network, so it gets the host check.
    if binary == "curl":
        urls = [p for p in parts[1:] if p.startswith(("http://", "https://"))]
        if not urls:
            return _refuse("curl call with no URL in it")
        for url in urls:
            if not ALLOWED_HOST_RE.match(url):
                return _refuse(f"curl may only reach the local clean-rag server, not {url!r}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
