"""Make shlex see the word boundaries a real shell sees.

Shared by the Bash guards that decide what a command actually invokes.

Python's shlex is a word splitter, not a shell parser: it breaks only on
whitespace and quotes, so ';', '|' and '&' are ordinary word characters to it.
A POSIX shell recognises those as control operators that delimit a token with
no whitespace required (Shell Command Language 2.3 Token Recognition: an
unquoted character that "can be used to form an operator" delimits the current
word). The two disagree on exactly the strings an attacker writes:

    shlex.split("true;git push")   -> ["true;git", "push"]
    a real shell                   -> run "true", then run "git push"

A guard that compares tokens against a binary name therefore never sees the
second command at all. Padding the operators with spaces first restores the
boundary before shlex runs, so the existing token-equality checks keep working
unchanged.

The contract, which is the part that matters and the part earlier versions of
this file did not have:

* A returned string has a space around every operator a shell would treat as
  one. Padding only ever ADDS separators, so a binary this returns can never
  hide one the caller would otherwise have found.
* When the quoting cannot be read to the end, this raises UnbalancedQuote
  rather than guessing. Guessing is what made this a security bug twice: the
  old scanner had no way to say "I don't know", so every gap in its model of
  shell quoting turned into a confident wrong answer, and the wrong answer was
  always in the unsafe direction -- it assumed the rest of the command was
  quoted and padded nothing at all.

Finding a boundary needs only the delimitation rules, not the meaning, of each
quoting form, so all three that a shell has are modelled here in full:

* '...'   a backslash has no special meaning, the span ends at the next quote,
          and nothing inside it is expanded or executed (POSIX 2.2.2).
* "..."   a backslash is special only before $, `, ", \\ or a newline, and is
          an ordinary character anywhere else (POSIX Shell Command Language
          2.2.3 Double-Quotes). Reading `\\"` as the end of the span is what
          let `echo "a\\"b";git push` walk past both guards.
* $'...'  ANSI-C quoting: a backslash escapes whatever follows it, so the span
          ends only at an UNescaped quote.

$"..." needs no case of its own: it is a double-quoted span with a locale
lookup, so the '$' falls through as an ordinary character and the '"' opens the
double-quoted span on the next pass, which is already the right reading.

Double quotes delimit a span; they do not make it inert. POSIX 2.2.3 says
double quotes "preserve the literal value of all characters within" EXCEPT
'$', '`' and '\\', and 2.6.3 Command Substitution says the shell "shall expand
the command substitution by executing command in a subshell environment". So
`$(...)` and `` `...` `` inside "..." are commands that really run:

    $ echo "prefix $(echo INNER_RAN) suffix"
    prefix INNER_RAN suffix
    $ echo '$(echo SHOULD_NOT_RUN)'
    $(echo SHOULD_NOT_RUN)

An earlier version copied a double-quoted span through verbatim, which read
`echo "$(git push origin main)"` as one inert argument and let a real push past
both guards. Such a substitution is now scanned as the command it is: the
literal run is closed, the substitution's body is padded under top-level rules
(so it can contain its own quoting, operators and further substitutions), and
the literal run is reopened afterwards. `echo "a $(git push) b"` becomes
`echo "a " $ ( git push )  " b"`, which shlex splits into tokens that include
a bare "git". Single quotes still suppress the substitution outright, so a
'...' span is still copied verbatim and `echo '$(git push)'` is still allowed.

The re-delimiting quotes are the one thing this adds beyond whitespace. Every
character of the input still survives in order, so the safety direction is
unchanged: it only ever splits one token into several, never merges two, and a
span it rewrites always contained a '$(' or a '`', neither of which appears in
any binary name a caller looks for, so no token that used to match can stop
matching.

Known limit, stated because a hand-rolled scanner over shell syntax is never
complete: a here-document body is scanned as ordinary text, so an operator
inside one is padded when a shell would not treat it as a separator. That
direction only invents a boundary, which costs a false refusal and cannot hide
an invocation, so it is left alone rather than modelled. Process substitution
(`<(cmd)`) is covered incidentally, since '(' and ')' are padded as operators
wherever they appear unquoted. See spec/architecture-changes/ for why this
scanner is kept rather than replaced by a real bash parser, and what the
ceiling on it is.

Padding is only half of what a guard needs. `split_readings` at the bottom of
this file is the other half: which shlex MODE the padded string is then read
in, which is a second place the two disagree, and on Windows it is the place
that costs.
"""

import shlex

# The POSIX control operators, plus the two command-substitution characters.
# Each starts a new command, so a binary name right after one is an invocation.
# Redirection ('<', '>') is deliberately absent: it introduces a filename, not
# a command, and padding it would only add noise.
_OPERATORS = frozenset(";|&()`\n")

# Inside "...", a backslash is special only before one of these. Before
# anything else it is a literal backslash that escapes nothing (POSIX 2.2.3).
#
# All three of '"', '$' and '`' are load bearing here. The '"' decides where
# the span ends. The other two decide whether a substitution runs at all:
# `echo "\$(git push)"` and ``echo "\`git push\`"`` pass literal text to echo,
# so an escape pair is consumed whole below and never opens a substitution.
# Do not collapse this set into the other two: the difference between an empty
# set and a full one is exactly what tells '...' from $'...'.
_DOUBLE_QUOTE_ESCAPES = frozenset('$`"\\\n')

# How a paren moves the nesting depth, so the ')' that closes a command
# substitution is told from one that closes a subshell inside it.
_NESTING_DELTA = {"(": 1, ")": -1}

# Inside '...', a backslash escapes nothing at all.
_NO_ESCAPES = frozenset()

# Inside $'...', a backslash escapes whatever follows it. Passed where the
# other spans pass a character set, and read by _copy_quoted_span as "any".
_EVERY_CHARACTER = None

# Global git flags that take their value as a SEPARATE argv token, so the
# subcommand sits one token further out than a skip-the-dashes scan finds
# (`git -C <path> commit -m ...`). Shared rather than duplicated per guard:
# both Bash guards have to walk a git invocation the same way, and the copy
# that lacked this set let `git -c user.name=x push` past quick-cop's
# read only cage. The fused form (`--git-dir=/x/.git`) is one token and needs
# no entry here.
GIT_VALUE_FLAGS = frozenset({"-C", "-c", "--git-dir", "--work-tree", "--namespace"})


class UnbalancedQuote(ValueError):
    """A quoted span in the command never closes, so its boundaries are unknown.

    Also raised for a command substitution that never closes, for the same
    reason: where the command inside it ends is not knowable from the text.

    A ValueError subclass on purpose: both callers already treat a ValueError
    off the tokenizer as "this command's structure cannot be read", and both
    refuse rather than allow on that path. Raising a type outside that
    hierarchy would land on a caller's last-ditch handler instead of its
    considered one.
    """


def git_subcommand(parts: list, start: int) -> tuple:
    """The git subcommand at parts[start], as (subcommand, index past it).

    Global flags are skipped, and so is the value of any flag that takes one,
    so `git -C /repo commit` reads as 'commit' rather than as '/repo'.
    Returns (None, len(parts)) when the invocation has no subcommand at all.
    """
    i = start + 1
    n = len(parts)
    while i < n:
        token = parts[i]
        if token in GIT_VALUE_FLAGS:
            i += 2
            continue
        if token.startswith("-"):
            i += 1
            continue
        return token, i + 1
    return None, n


def _copy_quoted_span(command: str, start: int, out: list, escapes) -> int:
    """Copy the quoted span opening at `command[start]` to `out` verbatim.

    Used for the two forms whose contents a shell never executes, '...' and
    $'...'. Returns the index just past the closing quote. `escapes` is the set
    of characters a backslash escapes inside this kind of span, or
    _EVERY_CHARACTER when a backslash escapes anything. Raises UnbalancedQuote
    if the span never closes.
    """
    quote = command[start]
    out.append(quote)
    i, n = start + 1, len(command)
    while i < n:
        char = command[i]
        if char == "\\" and i + 1 < n and (escapes is _EVERY_CHARACTER or command[i + 1] in escapes):
            out.append(command[i:i + 2])
            i += 2
            continue
        out.append(char)
        i += 1
        if char == quote:
            return i
    raise UnbalancedQuote(f"quoted span opened at index {start} never closes")


def _scan_double_quoted(command: str, start: int, out: list) -> int:
    """Scan the double-quoted span opening at `command[start]` into `out`.

    Literal text is copied through, because a shell does not read an operator
    inside quotes as one. A nested command substitution is not literal text
    (POSIX 2.2.3, 2.6.3), so the literal run is closed with a '"', the
    substitution is padded and scanned as a command, and the literal run is
    reopened. Returns the index just past the closing quote, and raises
    UnbalancedQuote if the span never closes.
    """
    out.append(command[start])
    i, n = start + 1, len(command)
    while i < n:
        char = command[i]
        if char == "\\" and i + 1 < n and command[i + 1] in _DOUBLE_QUOTE_ESCAPES:
            # A backslash-escaped '$' or '`' is literal text, so this pair is
            # consumed whole and never opens a substitution below.
            out.append(command[i:i + 2])
            i += 2
            continue
        if char == "$" and i + 1 < n and command[i + 1] == "(":
            # '" ' closes the literal run, ' "' reopens it, and the '$(' is
            # padded exactly as it would be at the top level, so every
            # character of the input survives in order.
            out.append('" ')
            out.append("$ ( ")
            i = _scan(command, i + 2, out, ")")
            out.append(" ) ")
            out.append(' "')
            continue
        if char == "`":
            out.append('" ')
            out.append("` ")
            i = _scan(command, i + 1, out, "`")
            out.append(" `")
            out.append(' "')
            continue
        out.append(char)
        i += 1
        if char == '"':
            return i
    raise UnbalancedQuote(f"quoted span opened at index {start} never closes")


def _open_quoted_span(command: str, i: int, out: list):
    """Scan the quoted span opening at `command[i]`, if one opens there.

    All three of a shell's quoting forms in one place, since the scan below
    treats them alike: each one delimits a region and hands back the index
    just past it. Returns None when `command[i]` opens no span at all.
    """
    char = command[i]
    if char == "$" and i + 1 < len(command) and command[i + 1] == "'":
        out.append(char)
        return _copy_quoted_span(command, i + 1, out, _EVERY_CHARACTER)
    if char == "'":
        return _copy_quoted_span(command, i, out, _NO_ESCAPES)
    if char == '"':
        return _scan_double_quoted(command, i, out)
    return None


def _scan(command: str, start: int, out: list, stop) -> int:
    """Pad every unquoted operator from `start` until `stop` closes the region.

    `stop` is None at the top level and the scan runs to the end of the string.
    Inside a command substitution it is ')' or '`', and the scan returns the
    index just past that character. A ')' closes only at nesting depth zero,
    so `$(echo $(git push))` ends where a shell ends it. A backquoted
    substitution ends at its own delimiter whatever the paren depth, because a
    shell does not require balanced parens inside one.
    """
    n = len(command)
    depth = 0
    i = start
    while i < n:
        char = command[i]
        past_span = _open_quoted_span(command, i, out)
        if past_span is not None:
            i = past_span
        elif char == "\\" and i + 1 < n:
            out.append(command[i:i + 2])
            i += 2
        elif char == stop and (stop != ")" or depth == 0):
            return i + 1
        elif char in _OPERATORS:
            depth += _NESTING_DELTA.get(char, 0)
            out.append(f" {char} ")
            i += 1
        else:
            out.append(char)
            i += 1
    if stop is not None:
        raise UnbalancedQuote(
            f"command substitution opened at index {start} never closes"
        )
    return i


def pad_shell_operators(command: str) -> str:
    """`command` with a space around every unquoted shell control operator.

    Quoted spans and backslash-escaped characters are left alone, because a
    shell does not treat an operator as one there either: `echo "a;b"` and
    `echo a\\;b` both pass a literal semicolon to echo rather than starting a
    second command. A command substitution nested in a double-quoted span is
    the exception, because a shell really does run it; see the module
    docstring.

    Raises UnbalancedQuote when a quoted span or a command substitution never
    closes, which is the one honest answer available: the boundaries after an
    unterminated quote are not knowable from the text, and reporting them as
    "none" is what a caller reads as "nothing to block here".
    """
    out = []
    _scan(command, 0, out, None)
    return "".join(out)


def split_readings(padded: str) -> tuple:
    """Every shlex reading of an already-padded command, and whether all parsed.

    Returned as (readings, complete). A caller walks every reading, because a
    binary hidden from one mode is usually plain in the other.

    POSIX mode alone is not enough, and the gap is not theoretical. POSIX mode
    treats a backslash as an escape, so it eats the separators out of a Windows
    path:

        shlex.split(r"C:\\Program Files\\Git\\bin\\git.exe push")
        -> ['C:Program', 'FilesGitbingit.exe', 'push']

    No token equals "git" after a caller strips path separators and '.exe', so
    a guard that matches on the binary name never sees the invocation at all.
    Python's own documentation says the module "is only designed for Unix
    shells" and that its behaviour is "not guaranteed to be correct ... on
    shells from other operating systems such as Windows"
    (https://docs.python.org/3/library/shlex.html). A fully qualified path to
    git.exe is the ordinary spelling on the platform this project mainly runs
    on, so this is the common case rather than an adversarial one.

    Non-POSIX mode keeps backslashes, which recovers the binary name from that
    path. It also leaves quotes attached to their token, so `echo "rm -rf x"`
    stays one quoted argument rather than becoming an invocation -- which is
    why both readings are walked instead of one replacing the other. A caller
    sees the union, and a union only ever ADDS a candidate binary, so the
    safety direction is refuse-more, never allow-more.

    The completeness flag is returned rather than discarded because a reading
    that failed is not a reading that found nothing: it is a command whose
    structure the caller could not see. Dropping the failed mode and treating
    what is left as a whole answer is choosing the more permissive parse, and
    that is what turned a bug in the padder into an allow on a real `git push`.
    What an incomplete read means is the caller's policy, not this function's:
    the two guards answer it differently and both are right for their own cage.
    """
    readings = []
    complete = True
    for kwargs in ({}, {"posix": False}):
        try:
            readings.append(shlex.split(padded, **kwargs))
        except ValueError:
            complete = False
    return readings, complete
