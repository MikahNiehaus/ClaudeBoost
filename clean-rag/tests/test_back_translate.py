"""back_translate.py: the three properties the draft got wrong, plus the hop files.

Offline. The endpoint is never touched: `translate()` takes an injected `fetch`
and `sleep`, and `main()` is run with `_request` patched on the module.

1. Chunks are budgeted on the percent encoded length. A CJK glyph is 9 URL
   characters, and the default chain has two legs that start from CJK text, so
   a raw character budget overruns the endpoint's silent truncation on exactly
   the hops that matter (measured on the live endpoint: 90 raw chars -> 394).
2. A 403 fails at once. It means the User-Agent was rejected and never clears.
   429 and 5xx retry with a backoff that grows.
3. Internal newlines survive: each returned segment carries its own, so the join
   keeps the source's line structure.
4. Every hop is written next to the destination.
"""

from __future__ import annotations

import importlib.util
import urllib.error
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "clean-rag" / "portable" / "skills" / "human-voice" / "scripts" / "back_translate.py"


@pytest.fixture(scope="module")
def bt():
    spec = importlib.util.spec_from_file_location("back_translate", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _http(code: int) -> urllib.error.HTTPError:
    return urllib.error.HTTPError("https://x", code, "err", {}, None)


def test_split_budgets_on_encoded_length_never_mid_sentence(bt):
    sentence = "签名注入将文本的平均得分从零点八二提高到零点九五零。"
    para = sentence * 40  # 1040 raw chars, far past CHUNK once encoded
    pieces = bt._split(para)
    assert len(pieces) > 1
    for piece in pieces:
        assert bt._encoded_len(piece) <= bt.CHUNK, "piece overruns the encoded budget"
        assert piece.endswith("。"), "split mid sentence"
    assert "".join(pieces) == para, "text lost or reordered by splitting"


def test_split_leaves_short_paragraph_alone(bt):
    assert bt._split("One. Two. Three.") == ["One. Two. Three."]


@pytest.mark.parametrize("sentence", [
    "This is amazing and great and wonderful and fantastic and awesome! ",
    "Is this thing really working correctly today? ",
    "This is a long line of text that keeps going and going.\n",
])
def test_split_recognizes_exclaim_question_and_bare_newline_boundaries(bt, sentence):
    # ADVERSARIAL: _split only treats "。" and ". " (period-space) as sentence
    # boundaries. A paragraph built entirely of "!"-, "?"-, or ".\n"-terminated
    # sentences has no such boundary, so the whole paragraph becomes one
    # "sentence" and _split emits it as a single piece with no budget check
    # applied within it -- exactly the silent-truncation failure this script
    # exists to prevent.
    para = sentence * 40
    assert bt._encoded_len(para) > bt.CHUNK, "test setup: paragraph must exceed budget"
    pieces = bt._split(para)
    for piece in pieces:
        assert bt._encoded_len(piece) <= bt.CHUNK, (
            "piece overruns the encoded budget (%d > %d) for sentence boundary %r"
            % (bt._encoded_len(piece), bt.CHUNK, sentence))
        assert piece.endswith(sentence), "split mid sentence"
    assert "".join(pieces) == para, "text lost or reordered by splitting"


def test_split_emits_lone_oversized_sentence_whole_and_warns(bt, capsys):
    # No boundary at all: spec says never mid sentence, so the piece goes out
    # whole and the endpoint's silent truncation is made loud on stderr.
    sentence = "word " * 500  # 2500 encoded chars, no terminator
    assert bt._split(sentence) == [sentence]
    assert "over the %d budget" % bt.CHUNK in capsys.readouterr().err


def test_403_fails_fast_without_retry(bt):
    calls, sleeps = [], []

    def fetch(piece, src, dst):
        calls.append(piece)
        raise _http(403)

    with pytest.raises(SystemExit, match="HTTP 403"):
        bt.translate("Hello.", "en", "de", fetch=fetch, sleep=sleeps.append)
    assert len(calls) == 1
    assert sleeps == []


def test_429_retries_with_growing_backoff_then_succeeds(bt):
    attempts, sleeps = [], []

    def fetch(piece, src, dst):
        attempts.append(1)
        if len(attempts) < 3:
            raise _http(429)
        return "Hallo."

    out = bt.translate("Hello.", "en", "de", fetch=fetch, sleep=sleeps.append, pause=0)
    assert out == "Hallo."
    assert len(attempts) == 3
    backoffs = sleeps[:2]  # the trailing pause sleep is not a backoff
    assert backoffs[1] > backoffs[0], "backoff did not grow: %r" % sleeps
    assert backoffs[0] >= 1.0


def test_5xx_exhausts_retries_then_exits(bt):
    def fetch(piece, src, dst):
        raise _http(503)

    with pytest.raises(SystemExit, match="HTTP 503"):
        bt.translate("Hello.", "en", "de", fetch=fetch, sleep=lambda s: None, retries=2)


LONG_PARA = "This is a normal English sentence with words. " * 60  # 3 pieces


@pytest.mark.parametrize("text", [
    "Line one.\nLine two.\n\nParagraph two.",
    "One.\n\nTwo.\n\nThree.",
    LONG_PARA,
    LONG_PARA + "\n\nShort.\n\n" + LONG_PARA,
    "A.\n\n\nB.",
    "\n\nA.\n\n",
    "A.\r\n\r\nB.",
    "A.\n\n   \n\nB.",
], ids=["internal-newline", "three-paras", "chunked-para", "chunked-around-short",
        "triple-newline", "leading-trailing-blank", "crlf-break", "whitespace-para"])
def test_translate_round_trips_structure_with_identity_fetch(bt, text):
    # A paragraph over CHUNK goes out as several requests, and the pieces of one
    # paragraph must be rejoined with "" while real paragraph breaks keep "\n\n".
    sent = []

    def fetch(piece, src, dst):
        sent.append(piece)
        return piece

    out = bt.translate(text, "en", "en", fetch=fetch, sleep=lambda s: None, pause=0)
    assert out == text
    assert all(bt._encoded_len(p) <= bt.CHUNK for p in sent), "a request overran the budget"
    assert len(sent) == sum(len(bt._split(p)) for p in text.split("\n\n") if p.strip())


def test_main_writes_every_hop_next_to_dest(bt, tmp_path, monkeypatch):
    src, dst = tmp_path / "in.txt", tmp_path / "out.txt"
    src.write_text("Hello there.\n\nSecond paragraph.", encoding="utf-8")
    monkeypatch.setattr(bt, "_request", lambda p, s, d: "[%s]%s" % (d, p))
    monkeypatch.setattr(bt.time, "sleep", lambda s: None)
    assert bt.main([str(src), str(dst), "--chain", "zh-CN,ja", "--pause", "0"]) == 0
    hops = sorted(p.name for p in tmp_path.glob("out.hop*.txt"))
    assert hops == ["out.hop1.zh-CN.txt", "out.hop2.ja.txt", "out.hop3.en.txt"]
    assert dst.read_text(encoding="utf-8").startswith("[en][ja][zh-CN]Hello")
