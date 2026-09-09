# kanban resolves the home directory at import, so the server cannot start without one

- **Kind:** architecture-change
- **Area:** server
- **Found by:** adversarial review on 2026-09-07, while testing `create_app`
- **Why it was not fixed in place:** the module's path constants are read by
  its handlers and by its poll loop, so making them lazy changes an interface
  other code in the module depends on, and the same eager pattern appears in
  `clean-rag/server/config.py`. Fixing one and leaving the other is worse than
  fixing neither, because it makes the class look handled.

## What is there now

`clean-rag/server/kanban.py:25` resolves the user's home directory while the
module is being imported:

```
CLAUDE_DIR = Path(os.environ.get("CLAUDE_HOME", Path.home() / ".claude"))
TASKS_DIR = CLAUDE_DIR / "tasks"
PROJECTS_DIR = CLAUDE_DIR / "projects"
```

`CLAUDE_HOME` is not the escape hatch it looks like. `Path.home() / ".claude"`
is the second argument to `os.environ.get`, so Python evaluates it before the
call, whether or not `CLAUDE_HOME` is set. Setting the variable changes the
result and does not avoid the call.

`create_app` imports the module unconditionally:

```
  app.py:1510: from .kanban import setup_kanban
  app.py:1511: setup_kanban(app)
```

`Path.home()` raises rather than returning a fallback when nothing resolves:

```
  File "...\Lib\pathlib\__init__.py", line 1261, in home
    raise RuntimeError("Could not determine home directory.")
RuntimeError: Could not determine home directory.
```

This is not new. `git diff HEAD -- clean-rag/server/kanban.py` is empty.

Reproduced by running the tests that call `create_app` with an explicitly
declared environment rather than the inherited one, which is the check that
makes an ambient dependency visible:

```
$ env -i PATH=... SYSTEMROOT=... TEMP=... COMSPEC=... PATHEXT=... APPDATA=... \
    python -m pytest clean-rag/tests/test_exec_routes_require_registered_project.py -q

        homedir = os.path.expanduser("~")
        if homedir == "~":
>           raise RuntimeError("Could not determine home directory.")
E           RuntimeError: Could not determine home directory.
C:\...\Lib\pathlib\__init__.py:1261: RuntimeError

FAILED ...::test_only_the_indexing_route_reaches_a_registry_writer
2 failed, 36 passed
```

The two that fail are the two that call `create_app`. Adding `USERPROFILE` back
to the same command turns them green, so the home directory is the whole of the
dependency.

## Why it is a problem

The blast radius is the server, not the test suite. Because the import sits in
`create_app` with no guard, a process with no resolvable home directory cannot
build the application at all: it fails during import, before any route exists,
before logging is configured, and with a `RuntimeError` that names the home
directory rather than the kanban feature that wanted it.

The environments where this bites are ordinary rather than exotic:

- A container run with no `HOME` set, which is the default for several base
  images when the process runs as a numeric uid with no `/etc/passwd` entry.
- A Windows service or scheduled task under an account with no loaded profile,
  where `USERPROFILE` is absent.
- A CI runner that scrubs the environment between steps.

The cost is out of proportion to the feature. Kanban is one optional surface
reading Claude Code's own task files. A server that indexes projects and serves
search has no reason to refuse to start because that surface cannot find a
directory it may never be asked to read.

An earlier review saw this only as a test isolation quirk. It is not: nothing
about the failure requires a test to be running.

## What to do instead

Two independent changes, in this order:

1. Make the paths lazy. Replace the module level constants with a function that
   resolves `CLAUDE_DIR` on first use and caches it, so importing the module
   costs nothing and only an actual kanban request can fail. `functools.cache`
   on a small resolver is the least disruptive shape, since the call sites read
   as constants today.
2. Make the import non fatal. `create_app` should treat kanban as optional:
   catch the failure, log it at warning with the reason, and serve every other
   route. A feature that cannot initialise should remove itself, not the
   server.

Doing only the second hides the first. Doing only the first leaves the next
module level `Path.home()` free to take the server down.

Files: `clean-rag/server/kanban.py`, `clean-rag/server/app.py`. Check
`clean-rag/server/config.py` in the same pass for the same pattern.

## What it would break

- Anything reading `kanban.CLAUDE_DIR`, `kanban.TASKS_DIR` or
  `kanban.PROJECTS_DIR` as module attributes, including any test that
  monkeypatches them. A resolver function is not patchable the same way, so
  those call sites move.
- A test that relied on the import failing loudly would stop failing. That is
  the point, but it means the failure needs somewhere else to be asserted: a
  test that builds the app with no home resolvable and expects the other routes
  to be served.
- The warning log becomes the only signal that kanban is absent, so a real
  misconfiguration gets quieter. That is the accepted cost of a feature
  degrading instead of the server refusing to start, and it is the reason the
  log has to name the cause and not just the feature.

## Open questions

- Whether kanban should be behind an explicit setting rather than always
  registered. If it is optional enough to disable itself on failure, it may be
  optional enough to be opt in, which would make the whole import conditional
  and this simpler.
- Whether `clean-rag/server/config.py` has the same eager read. It was not
  audited here, and fixing kanban alone would leave the class open.
