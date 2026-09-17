# The install aliasing guard checks the file it writes, never the directory it writes into

- **Kind:** architecture-change
- **Area:** scripts
- **Found by:** bad-cop on 2026-09-17, reproduced end to end
- **Why it was not fixed in place:** it is a policy decision about what an
  installer owes a user whose `~/.claude` is someone else's tracked directory,
  and the two obvious answers each break a real setup. The codebase currently
  holds both answers in different files.

## What is there now

`clean-rag/install.py:139` `_alias_description(path)` reports how writing a path
would rewrite a different file. It tests three mechanisms on the FINAL path
component only: `path.is_symlink()`, then `os.path.isjunction(path)`, then
`os.stat(path, follow_symlinks=False).st_nlink > 1`. `_copy_file` warns and
refuses to copy when it returns anything.

The docstring at `clean-rag/install.py:148` states the exclusion as settled:

> Only the final path component is examined, deliberately. os.path.realpath
> would also flag an ordinary file whose PARENT is aliased ... Refusing on that
> would break every install for anyone who keeps ~/.claude behind a junction or
> a dotfiles symlink, which is a normal setup. Aliasing of the parent is the
> user's own arrangement and writing files into it is exactly what this
> installer is for.

`scripts/setup.py:317`, in `sync_slash_commands`, answers the same question the
opposite way for a directory destination:

```python
# If dst is a Windows junction or POSIX symlink to the repo, leave it alone —
# the repo IS the source of truth in that case, no copy needed.
if dst.exists() and (dst.is_symlink() or _is_junction(dst)):
    _skip("slash commands - dst is a link/junction; skipping copy")
    return
```

So one installer refuses to write through an aliased directory and the other
writes through it without a word.

## Why it is a problem

It is a silent overwrite of a file the installer does not own, and it has been
reproduced rather than predicted. With `~/.claude` a junction into a directory
another tool tracks, and a `CLAUDE.md` already there that differs from the
bundled copy and is older:

```
mklink rc: 0 Junction created for ...\home\.claude <<===>> ...\other_tracked_repo_dot_claude
before: SOMEONE ELSE'S TRACKED FILE, DO NOT TOUCH
  [OK] installed .claude\CLAUDE.md
after:  bundled CLAUDE.md
alias verdict for the file itself: None
```

`_alias_description` returns `None` correctly by its own contract, because the
file is not a symlink, junction or hard link. The mtime branch does not fire
because the destination is older. So `shutil.copy2` runs and the only thing the
user sees is `[OK] installed`, identical to an ordinary success.

The asymmetry is the sharper half. At the file level ANY aliasing stops the copy
and prints a warning, even when the content already differs. One directory level
up, aliasing is invisible by design and the copy proceeds silently, against the
same kind of divergent older destination. The consequence has the same shape,
a write through to a file the installer does not own. Only one of the two is
checked.

`realpath` would catch it, and the docstring's reason for not using `realpath`
is true as far as it goes. Measured here: a plain file inside a junction really
does have `realpath != abspath` while the file itself is ordinary
(`is_symlink False / isjunction False / nlink 1`). So `realpath` alone cannot
separate "my dotfiles live behind a symlink, which is fine" from "this directory
belongs to another repo, which is not".

## What to do instead

Pick one policy and apply it in both installers, rather than leaving
`clean-rag/install.py` and `scripts/setup.py` disagreeing.

Three shapes, in increasing cost:

1. **Warn, do not refuse.** Detect an aliased parent with `realpath` and print
   the destination's real path once per run before copying. Cheap, breaks no
   setup, and turns a silent overwrite into a visible one. Does not prevent the
   overwrite.
2. **Refuse on an aliased parent when the destination content differs.**
   Borrows the existing content check: an identical file is a no-op either way,
   so only a real divergence stops the run. Narrower than `setup.py`'s blanket
   skip, and it does not punish the common dotfiles arrangement where the
   content already matches.
3. **Match `setup.py:317` exactly and skip whenever the parent is aliased.**
   Consistent, and the strictest. It is also the option most likely to break a
   legitimate install, which is precisely what good-cop was avoiding.

Files it would touch: `clean-rag/install.py` (`_alias_description` or
`_copy_file`), `scripts/setup.py:317` if the policy is unified,
`clean-rag/tests/test_install_user_asset_copy.py`.

## What it would break

- `clean-rag/install.py:_copy_file` currently installs successfully for every
  user whose `~/.claude` is a symlink or junction. Options 2 and 3 stop some of
  those installs. That population is not measured, and the docstring's claim
  that it is "a normal setup" is an assertion nobody has checked.
- `clean-rag/tests/test_install_user_asset_copy.py` has 17 tests built around
  the current per file contract. Option 3 changes what several of them assert.
- `scripts/setup.py:317`'s skip is load bearing for the documented workflow
  where the repo is the source of truth for slash commands. Relaxing it to match
  option 1 or 2 would start copying into a junction that deliberately points at
  the repo.

## Open questions

- Which of the two existing behaviours is the intended one? The codebase does
  not say. `setup.py:317`'s comment argues the link means the repo is canonical
  and no copy is needed. `install.py:148` argues the link is the user's own
  arrangement and writing into it is the point. Both are reasonable and they
  cannot both be right for the same class of destination.
- How common is a symlinked or junctioned `~/.claude` among real users? That
  number decides whether option 3 is safe or hostile, and nobody has it.
- Does the same hazard exist on the POSIX install path, or only on Windows
  where `install.bat` creates links itself? Not investigated.
- `os.path.isjunction` is 3.12 and newer, guarded with `getattr`. On older
  Python a junction goes undetected. bad-cop judged this decorative at the real
  call sites, because `mklink /J` against a file target produces a reparse point
  where `os.path.exists()` is already False, so `_copy_file:192` excludes it
  first. That reasoning holds for the file destinations this installer writes
  today, and stops holding the moment a directory destination is added.
