# Reading a port number from server.config imports torch, on every prompt and every edit

- **Kind:** bloat
- **Area:** hooks
- **Found by:** audit of the skill and capability surface, 2026-09-11
- **Why it was not fixed in place:** it was not. This one is below the bar and
  should just be fixed. It is filed here because it is the headline measurement
  of the wider audit and the other items reference it.
- **Status: DONE, 2026-09-16.** Fixed and re-measured. The numbers below are
  the original finding and are kept for the reasoning; see "Done" at the bottom
  for what the code does now and what it costs.

## What is there now

`clean-rag/server/config.py:105` runs device detection at module import:

```python
def _detect_device() -> str:                    # config.py:89
    override = os.environ.get("CLEAN_RAG_DEVICE", "").strip()
    if override:
        return override
    try:
        import torch                            # config.py:95
        if torch.cuda.is_available():
            return "cuda"
        ...

DEVICE: str = _detect_device()                  # config.py:105
```

So importing `server.config` for any reason imports torch and probes CUDA.

Many files import `server.config`, including `cli/server_ctl.py:61,69`,
`install.py:1254`, `server/embedding.py:62,128` and eight tests. All of them pay
the same cost, so the fix is worth more than the hook count alone suggests.

Four of them are the hooks, and they share a distinct shape: a `try/except` with
a hardcoded fallback, wrapped around a single constant. Three want
`STANDALONE_PORT`, which is `int(os.environ.get("CLEAN_RAG_PORT", "8613"))` at
`config.py:72`:

| File | Line | Wants | Hook event |
|---|---|---|---|
| `scripts/prompt-rules-injector.py` | 85 | `STANDALONE_PORT` | UserPromptSubmit |
| `scripts/context-nudge.py` | 69 | `STANDALONE_PORT` | PostToolUse `.*` |
| `scripts/boost-run.py` | 52 | `STANDALONE_PORT` | `/boost` |
| `clean-rag/hooks/graph-context-inject.py` | 132 | `DATABASES_DIR` | PreToolUse Edit |

Each wraps the import in `try/except` with a hardcoded `8613` fallback, so the
import is not even load bearing. It exists so the number is not written down
twice. `context-nudge.py:60-62` says so directly: "Written down here once
before, as 8612, and left behind when that server was retired."

## Why it is a problem

Measured, with `-X importtime` and by running each registered hook against a
realistic payload:

```
bare python start                                0.06s
from server.config import STANDALONE_PORT        5.62s
  of which torch                                 4.72s
```

That lands on two hooks that run constantly:

```
UserPromptSubmit   6 hooks  8.24s total, of which prompt-rules-injector.py  5.91s
PreToolUse (Edit)  5 hooks  7.43s total, of which graph-context-inject.py   6.43s
PostToolUse (Edit) 7 hooks  1.23s
Stop               9 hooks  1.48s
```

**A single edit turn spends about 18.4 seconds in hooks.**

How much of that is torch was then measured directly rather than inferred.
`config.py:90-92` returns the `CLEAN_RAG_DEVICE` override before reaching
`import torch`, so running each hook twice, once with that variable set, gives
the torch cost as a difference:

```
prompt-rules-injector.py     6.74s -> 0.12s    torch 6.61s
graph-context-inject.py      7.55s -> 0.62s    torch 6.93s
                            ------    -----
the pair                    14.29s    0.75s    torch 13.54s
```

**About 13.5 of the 18.4 seconds is device detection.** An edit turn would be
roughly 4.8 seconds of hooks without it.

A second run on a loaded machine measured the same pair at 16.3s falling to
2.2s, a difference of 14.1s. The absolute numbers move with machine load. The
difference does not, and the difference is the finding.

That also means a mitigation exists today, with no code change: setting
`CLEAN_RAG_DEVICE=cpu` in the environment skips the probe. It is a workaround
rather than the fix, because it makes every reader of `DEVICE` take the override
whether or not that machine has a GPU.

The `try/except` makes the defect worse rather than better. The fallback means
nobody ever sees an error, so the cost has no symptom other than the system
feeling slow. Nothing in the transcript says why.

`context-nudge.py` measured at 0.17s in the probe, so its `_rag_port()` is not
on the path that payload took. It is registered on PostToolUse `.*`, so it pays
the same 4.7s on whichever paths do call it.

## What to do instead

Make the device probe lazy. `DEVICE` has exactly one reader,
`clean-rag/server/embedding.py:128`, and it reads it inside a function at model
load time:

```python
from server.config import DEVICE, EMBED_BATCH_SIZE   # embedding.py:128
kwargs: dict = {"device": DEVICE}                    # embedding.py:132
```

Replace the module level `DEVICE` with a cached `get_device()` and call it from
`embedding.py`. One file changes, one caller updates, and `import server.config`
becomes free.

Do that rather than removing the imports from the four hooks. Keeping the port
in one place is correct, and it is the reason those imports exist. The defect is
that a config module does hardware detection at import, not that hooks read
config.

Files: `clean-rag/server/config.py`, `clean-rag/server/embedding.py`.

## What it would break

`clean-rag/server/embedding.py:128-132` is the only reader of `DEVICE` in the
tree, confirmed by grep across `clean-rag/**/*.py` excluding the venv. Two files
mention the name at all, and one of them is `config.py` itself.

Anything reading `config.DEVICE` as an attribute after import would need to
change to the call. Nothing currently does.

The `CLEAN_RAG_DEVICE` override at `config.py:91` keeps working either way, and
becomes the fast path for anyone who sets it.

## Open questions

Whether `PIPELINE_VERSION`, `CODE_EMBEDDING_MODEL` and the other constants in
that file should move to a module with no runtime behaviour at all, so that
"read a constant" can never again mean "load a machine learning framework". The
narrow fix above does not prevent the next function like `_detect_device` from
being added beside them.

## Done, 2026-09-16

`DEVICE: str = _detect_device()` at module scope is gone. `server/config.py`
now exposes `get_device()`, resolved on first use and `@functools.cache`d, and
its docstring records the original cost. `_detect_device` is unchanged and still
honours the `CLEAN_RAG_DEVICE` override first.

Re-measured 2026-09-16, warm, on the same machine:

| | original finding | now |
|---|---|---|
| `import server.config` | 4.7s | 0.19s |
| all six per-edit hooks together | 18.4s | 2.15s |

Per hook, warm: `research-gate.py` 0.20s, `graph-context-inject.py` 0.36s,
`code-pattern-inject.py` 0.37s, `tdd-guard.py` 0.54s, `consult-gate.py` 0.39s,
`context-nudge.py` 0.29s. A bare interpreter start is 0.07s, so roughly a third
of what remains is process startup that no change to this file can reach.

**Read those numbers as warm, not typical.** The same six measured cold, on
their first invocation of a session, came to 5.72s, with `tdd-guard.py` at
1.92s and `code-pattern-inject.py` at 1.60s rather than the sub-0.6s figures
above. The gap is filesystem cache and bytecode compilation, not this fix. A
session's first edit still pays it.

The open question above is untouched by this and still stands.
