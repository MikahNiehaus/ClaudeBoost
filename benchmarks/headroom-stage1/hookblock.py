"""§7.1: is there anything left to compress on the hook-injection side?

`rag-enforce.py` is the hook that injects RAG results into every user prompt, so
it is the other half of the "compress what we inject" idea. This runs it on three
real prompts, measures the block it emits with the SAME tokenizer measure.py
uses, and then asks headroom to compress it and records what headroom actually
did.

The answer is not a threshold argument. The block clears both no-op gates
(`min_tokens_to_crush` 200, `min_tokens_to_compress` 250) and headroom still
leaves it byte-identical, for two structural reasons this script records rather
than asserts: SmartCrusher only rewrites arrays of dicts and the block is prose,
and `compress()`'s router classifies it as protected content.

Its size is capped by the hook itself -- `rag-enforce.py` formats `results[:3]`
with `content[:250]` each (search for `[:250]` in `_format_rag_results`) -- which
is why the byte count is identical across prompts while the token count is not.

Needs clean-rag up on 127.0.0.1:8613 with this repo indexed, since the block is
built from live search results.

Side effect: the hook opens a research-turn record under the synthetic session id
below, in clean-rag's gitignored `state/research/`. It expires in an hour
(`research_state.TURN_MAX_AGE_S`) and no real session uses that id.
"""
from __future__ import annotations

import json
import pathlib
import subprocess
import sys

from headroom import CompressConfig, compress
from headroom.providers.anthropic import AnthropicProvider
from headroom.transforms.smart_crusher import SmartCrusher, SmartCrusherConfig

HERE = pathlib.Path(__file__).parent
REPO = HERE.parent.parent
HOOK = REPO / "clean-rag" / "hooks" / "rag-enforce.py"
MODEL = "claude-sonnet-4-5-20250929"
SESSION = "headroom-stage1-hookblock"

# The three prompt intents researcher/swiper actually run under.
PROMPTS = {
    "bugfix": "fix the null reference in the reputation scoring path",
    "newfeature": "add an endpoint that returns a project's index status",
    "refactor": "this function is getting too complex, what patterns does our codebase use",
}

# Declared, not inherited. The hook reads CLEAN_RAG_HOME, CLAUDEBOOST_HOME and
# CLEAN_RAG_PORT, and leaving all three unset is what makes it resolve to this
# repo and the default port. A developer shell also carries CLAUDEBOOST_* toggles
# that change hook behaviour, so inheriting the environment would make the
# measurement depend on whatever happens to be exported -- the undeclared
# dependency CLAUDE.md and scripts/tests/helpers.py::hook_env both exist to stop.
HOOK_ENV = {"PATH": "/usr/bin:/bin", "HOME": str(pathlib.Path.home())}

tok = AnthropicProvider().get_token_counter(MODEL)
crusher = SmartCrusher(config=SmartCrusherConfig())


def emit(prompt: str) -> str:
    """Run the real hook on a real prompt and return the block it injects."""
    payload = json.dumps({"hook_event_name": "UserPromptSubmit", "prompt": prompt,
                          "cwd": str(REPO), "session_id": SESSION,
                          "transcript_path": "/dev/null"})
    done = subprocess.run([sys.executable, str(HOOK)], input=payload, env=HOOK_ENV,
                          capture_output=True, text=True, timeout=180)
    if done.returncode != 0:
        raise RuntimeError(f"{HOOK.name} exited {done.returncode}: {done.stderr.strip()[:400]}")
    return done.stdout


rows = []
for intent, prompt in PROMPTS.items():
    block = emit(prompt)
    before = tok.count_text(block)
    crushed = crusher.crush(block, query="", bias=1.0)
    msgs = [{"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": prompt},
            {"role": "tool", "tool_call_id": "call_0", "content": block}]
    res = compress(msgs, model=MODEL, config=CompressConfig())
    after_tool = next((m["content"] for m in res.messages
                       if m.get("role") == "tool" and isinstance(m.get("content"), str)), "")
    rows.append({
        "intent": intent,
        "prompt": prompt,
        "bytes": len(block.encode()),
        "tokens": before,
        "crusher_strategy": crushed.strategy,
        "crusher_modified": crushed.was_modified,
        "crusher_tokens_after": tok.count_text(crushed.compressed),
        "compress_transforms": sorted(set(res.transforms_applied)),
        "compress_tokens_after": tok.count_text(after_tool),
        "byte_identical": crushed.compressed == block and after_tool == block,
    })

out_path = HERE / "hookblock_results.json"
out_path.write_text(json.dumps({"model": MODEL,
                                "tokenizer": "tiktoken cl100k_base x1.1 (APPROXIMATE)",
                                "hook": str(HOOK.relative_to(REPO)),
                                "blocks": rows}, indent=2))

print(f"{len(rows)} real rag-enforce.py blocks, one per prompt intent\n")
for r in rows:
    print(f"{r['intent']:<11} {r['bytes']:>5,} bytes  {r['tokens']:>4} tokens   "
          f"crusher={r['crusher_strategy']} (modified={r['crusher_modified']})   "
          f"compress={r['compress_tokens_after']} tokens after")
    print(f"{'':11} router: {', '.join(r['compress_transforms'])}")
sizes = {r["bytes"] for r in rows}
print(f"\nbytes: {'identical across prompts at ' + f'{sizes.pop():,}' if len(sizes) == 1 else sorted(sizes)}"
      f"   tokens: {min(r['tokens'] for r in rows)}-{max(r['tokens'] for r in rows)}")
print(f"left byte-identical by both paths: {sum(r['byte_identical'] for r in rows)}/{len(rows)}")
print(f"\nfull results -> {out_path}")
