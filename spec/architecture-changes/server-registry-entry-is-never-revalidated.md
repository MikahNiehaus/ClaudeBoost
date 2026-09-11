# A registry entry authorises a path string, never the directory it named

- **Kind:** architecture-change
- **Area:** server
- **Found by:** adversarial review on 2026-09-07, against `_registered_project_or_error`
- **Why it was not fixed in place:** changes what `state/projects.json` has to
  record and therefore the contract between `indexing._update_project_registry`
  (the writer) and every reader of the registry, including
  `clean-rag/server/auto_reindex.py` and `clean-rag/server/reindex_unit.py`.

## What is there now

`_registered_project_or_error` (`clean-rag/server/app.py:777`) is the whole
control on the routes that execute a project's own tooling. It normalises the
requested path and compares it against the `project_path` string of each
registry entry:

```
        wanted = _normalized_path_key(project_path)      # app.py:822
    for entry in _list_projects().values():              # app.py:827
            if _normalized_path_key(registered) == wanted:   # app.py:832
                return None
```

The entry `indexing._update_project_registry` writes
(`clean-rag/server/indexing.py:1448`) carries more than the path:
`files_indexed`, `chunks_created` and an `indexed_at` timestamp. The gate reads
none of them. Confirmed by inspecting the function body for every field that
could support a freshness or identity check:

```
  gate body mentions 'indexed_at':    False
  gate body mentions 'st_mtime':      False
  gate body mentions 'hash':          False
  gate body mentions 'st_ino':        False
  gate body mentions 'files_indexed': False
```

## Why it is a problem

Registration means "this server indexed this directory" at the moment it was
written. The gate reads it as "this directory is trusted now". A path is not a
stable identifier for a directory, so those are different statements and
nothing narrows the gap between them.

Reproduced end to end in a scratch tree: register a legitimate project, replace
the directory at that path with different content, then call the executing
route. The registry was never touched.

```
 registered: ...\legit-project
 registry entry fields: ['files_indexed', 'indexed_at', 'project_path', 'source']
 same path now holds different content, registry untouched
 handle_run_tests -> 200
 replaced content executed: True
```

The framing that matters is not an attacker who can already write to that path.
`_registered_project_or_error`'s own docstring accepts that "any process
already running as this user can do anything this server can", and rewriting a
directory is inside that. The realistic case is an entry that goes stale on its
own, where nobody did anything wrong:

- A network or shared drive whose mount is replaced.
- A repository the operator stopped trusting, or handed to someone else, and
  never removed from the registry. Nothing prompts for that, and there is no
  route that removes an entry.
- A path whose parent directory permissions changed so a second account can
  write into it.
- A registration made from a scratch or temp directory whose name is later
  reused by a different tool.

In each of those the operator's decision to trust was made about a directory
that no longer exists, and `/run-tests` still executes whatever is at the name.

## What to do instead

Record identity at registration and check it at use. The smallest version that
matches how the registry is already written:

- `_update_project_registry` (`clean-rag/server/indexing.py:1448`) stores a
  cheap directory identity alongside `indexed_at`. `st_ino` plus `st_dev` is
  the portable form on POSIX; on Windows the equivalent is the file index from
  `GetFileInformationByHandle`, which `os.stat` exposes as `st_ino` on recent
  CPython. A hash of the manifest is the more meaningful alternative and costs
  a read.
- `_registered_project_or_error` (`clean-rag/server/app.py:777`) compares it and
  refuses on a mismatch with a message naming re indexing as the fix, matching
  the wording it already uses for an unregistered path.
- Decide separately whether an entry should also expire on age. Time is a weak
  proxy for identity and would refuse a legitimate long lived project, so it
  probably should not.

Files: `clean-rag/server/indexing.py`, `clean-rag/server/app.py`, and the
registry readers that would see the new field,
`clean-rag/server/auto_reindex.py` and `clean-rag/server/reindex_unit.py`.

## What it would break

- Every existing entry in every installed `state/projects.json` lacks the new
  field. The gate has to treat a missing identity as acceptable or every
  installed project stops working on upgrade until it is re indexed, and
  accepting it silently means the check does nothing until every entry is
  rewritten.
- `clean-rag/hooks/auto-test-gate.py` posts the session's git root to
  `/run-tests` on every Stop and is the one Stop hook here that genuinely
  blocks. A false refusal from a stale identity turns into a blocked turn, so
  the mismatch path has to be certain before it refuses.
- A directory identity changes for benign reasons. A `git clone` to a fresh
  path, a restored backup, a container rebuild and a bind mount all produce a
  new inode for the same project, so this trades an unnoticed stale trust for a
  visible false refusal. That trade is the decision this file is asking for.
- `clean-rag/tests/test_exec_routes_require_registered_project.py` registers
  projects by writing the registry directly (`_register`), so its fixtures
  would need the new field.

## Open questions

- Whether it is worth it at all, given the trust model already concedes local
  code execution. The argument for yes is that the stale entry cases above need
  no attacker, only time.
- Whether the fix belongs on the gate or on the registry. An entry that fails
  revalidation is arguably garbage the sweep in
  `clean-rag/server/auto_reindex.py` should remove, which would make the gate's
  simple membership test correct again rather than adding a second check.
- Whether `st_ino` is dependable enough on Windows across the filesystems this
  runs on to base a refusal on.
