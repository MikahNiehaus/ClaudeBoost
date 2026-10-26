"""python -m pytest test_pipeline.py  checks validate.py rules and the render and finalize output gates."""
import copy
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import validate  # noqa: E402

FFMPEG = shutil.which("ffmpeg")
needs_ffmpeg = pytest.mark.skipif(not (FFMPEG and shutil.which("ffprobe")), reason="ffmpeg and ffprobe not on PATH")

TEXTS = ["intro talk", "ten things matter", "we saw 15 cases", "a search", "a walk", "a trace", "a code", "the end"]


def para(i, text):
    words = [{"w": f"w{k}", "s": i * 10.0 + k * 0.5, "e": i * 10.0 + k * 0.5 + 0.4} for k in range(20)]
    return {"index": i, "spoken": True, "start": i * 10.0, "text": text, "words": words}


MAP = {"duration": 80.0, "paragraphs": [para(i, t) for i, t in enumerate(TEXTS)]}
SCENES = [
    {"kind": "title", "para": 0, "title": "Intro"},
    {"kind": "bullets", "para": 1, "items": ["one", "two", "three"]},
    {"kind": "stat", "para": 2, "value": "15", "label": "cases"},
    {"kind": "search", "para": 3, "query": "q", "docs": [{"text": "a", "score": 0.5}, {"text": "b", "score": 0.2}], "pick": [0]},
    {"kind": "walk", "para": 4, "nodes": ["a", "b", "c"], "edges": [[0, 1]], "path": [0, 1]},
    {"kind": "trace", "para": 5, "nodes": ["a", "b", "c"], "data": ["1", "2", "3"]},
    {"kind": "code", "para": 6, "lines": ["def f(x):", "    return x + 1"]},
    {"kind": "bars", "para": 7, "bars": [{"label": "a", "value": 3}]},
]


def errors(i=None, mp=MAP, **change):
    scenes = copy.deepcopy(SCENES)
    if i is not None:
        scenes[i].update(change)
    return validate.check_data({"scenes": scenes}, mp)[0]


def with_text(i, text):
    mp = copy.deepcopy(MAP)
    mp["paragraphs"][i]["text"] = text
    return mp


def test_baseline_passes():
    assert errors() == []


@pytest.mark.parametrize("i,field,value", [
    (0, "title", {"a": "b"}), (2, "label", {"a": "b"}), (1, "heading", {"a": "b"}), (2, "note", 123),
    (7, "unit", {"a": "b"}), (0, "subtitle", ["x"]), (2, "value", ["15"]),
])
def test_wrong_field_type_is_rejected(i, field, value):
    assert any(f"{field} must be" in e for e in errors(i, **{field: value}))


@pytest.mark.parametrize("change", [
    {"w": 1.5}, {"w": "1"}, {"w": -1}, {"w": True}, {"cues": 3}, {"cues": ["a"]}, {"cues": [True, 2]},
    {"cues": [1.5]}, {"para": [1]}, {"para": True}, {"kind": ["bullets"]},
])
def test_malformed_timing_fields_are_errors_not_crashes(change):
    assert errors(1, **change)


@pytest.mark.parametrize("change,want", [
    ({"cues": [3, 2]}, "strictly increasing"), ({"cues": [3, 3]}, "strictly increasing"), ({"cues": [20]}, "cue 20 out of range"),
    ({"items": ["one two three four five six seven eight"]}, "item over 7 words"),
])
def test_cue_order_range_and_item_length(change, want):
    assert any(want in e for e in errors(1, **change))


def test_valid_cues_pass():
    assert errors(1, cues=[0, 5, 19]) == []


def test_scene_that_is_not_an_object():
    scenes = copy.deepcopy(SCENES)
    scenes[1] = "bullets"
    assert "scene 1: must be an object" in validate.check_data({"scenes": scenes}, MAP)[0]


def test_bars_max_below_a_value():
    assert any("max must be at least" in e for e in errors(7, max=1))


@pytest.mark.parametrize("lines,want", [
    (["x = 1"] * 9, "1 to 8 lines"), (["x" * 61], "over 60 characters"), (["y = a-b"], "hyphenated"), ([], "1 to 8 lines"),
])
def test_code_limits(lines, want):
    assert any(want in e for e in errors(6, lines=lines))


def test_code_at_the_limits_passes():
    assert errors(6, lines=["x" * 60] * 8) == []


@pytest.mark.parametrize("value,text,ok", [
    ("10", "ten things", True), ("10", "10 things", True), (99, "we saw 99 cases", True),
    ("2.5", "two point five times", True), ("1,000", "one thousand rows", True), ("40%", "forty percent", True),
    ("15", "fifteen cases", True), (99, "we saw 15 cases", False), ("5", "we saw 15 cases", False),
    ("5", "twenty five cases", False), ("5", "fifteen cases", False), ("2", "two point five", False),
    ("10", "a hundred cases", False),
])
def test_card_numbers_must_be_spoken(value, text, ok):
    errs = errors(2, mp=with_text(2, text), value=value)
    assert (not any("not spoken" in e for e in errs)) == ok, errs


def test_numbers_in_heading_are_gated():
    assert any("number 7 not spoken" in e for e in errors(1, heading="7 rules"))


@pytest.mark.parametrize("i,change,want", [
    (7, {"bars": [{"label": "a", "value": float("inf")}]}, "bars must be"),
    (7, {"bars": json.loads('[{"label": "a", "value": 1e999}]')}, "bars must be"),
    (7, {"bars": [{"label": "a", "value": 10 ** 400}]}, "bars must be"),
    (7, {"max": float("inf")}, "max, or the largest"),
    (2, {"value": float("nan")}, "value must be"),
    (2, {"value": float("-inf")}, "value must be"),
    (3, {"docs": [{"text": "a", "score": float("nan")}]}, "docs must be"),
])
def test_non_finite_numbers_are_rejected(i, change, want):
    assert any(want in e for e in errors(i, **change))


def test_graph_edge_indexes_are_not_card_numbers():
    graph = {"kind": "graph", "nodes": ["a", "b", "c"], "edges": [[0, 1], [1, 2]], "layout": "cycle"}
    assert errors(1, **graph) == []
    assert any("number 7 not spoken" in e for e in errors(1, **graph, heading="7 hops"))


@pytest.mark.parametrize("line", ["a\n" * 30, "\t" * 60, "x\ry", "a b", "a\x00"])
def test_code_line_with_tab_or_line_break_is_rejected(line):
    assert any("tab, line break or control character" in e for e in errors(6, lines=[line]))


@pytest.mark.parametrize("digits", [3000, 5000])
def test_long_digit_runs_are_errors_not_crashes(digits):
    assert any("not spoken" in e for e in errors(1, heading="9" * digits))


def write(path, body):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body)


@pytest.mark.parametrize("args,files,want", [
    (["validate.py"], {}, "python validate.py name"),
    (["validate.py", "nope"], {}, "storyboards/nope.json not found"),
    (["validate.py", "x"], {"storyboards/x.json": "{bad", "map/x.json": "{}"}, "storyboards/x.json is not valid JSON"),
    (["validate.py", "x"], {"storyboards/x.json": '{"scenes": []}', "map/x.json": '{"duration": 1}'}, "KeyError 'paragraphs'"),
    (["outline.py"], {}, "python outline.py name"),
    (["outline.py", "nope"], {}, "map/nope.json not found"),
    pytest.param(["map.py", "nope"], {}, "align/nope.json not found", marks=needs_ffmpeg),
    (["map.py"], {}, "no align/*.json"),
    (["render.py"], {}, "the following arguments are required"),
    (["render.py", "nope"], {}, "storyboards/nope.json not found"),
    (["render.py", "x"], {"storyboards/x.json": '{"scenes": [{"value": Infinity}]}', "map/x.json": '{"duration": 1, "paragraphs": []}'},
     "Out of range float"),
    (["align.py"], {}, "python align.py"),
    pytest.param(["align.py", "x.mp3", "y.json"], {"x.mp3": "junk"}, "ffmpeg could not decode", marks=needs_ffmpeg),
    (["finalize.py", "--mx"], {}, "usage: python finalize.py"),
])
def test_bad_input_exits_non_zero_with_one_line(tmp_path, args, files, want):
    copy_scripts(tmp_path)
    for name, body in files.items():
        write(tmp_path / name, body)
    tools = [Path(t).parent for t in (FFMPEG, shutil.which("ffprobe")) if t]
    r = subprocess.run([sys.executable, *args], cwd=tmp_path, env=clean_env(*tools), capture_output=True, text=True)
    assert r.returncode != 0 and want in r.stderr and "Traceback" not in r.stderr, r.stderr


@needs_ffmpeg
def test_finalize_reports_audio_without_duration(tmp_path):
    copy_scripts(tmp_path)
    write(tmp_path / "audio" / "demo.mp3", "junk")
    (tmp_path / "out").mkdir()
    make(tmp_path / "out" / "demo.mp4", 2, video=True)
    env = clean_env(Path(FFMPEG).parent, Path(shutil.which("ffprobe")).parent)
    r = subprocess.run([sys.executable, "finalize.py"], cwd=tmp_path, env=env, capture_output=True, text=True)
    assert r.returncode == 1 and "audio has no duration" in r.stdout and "Traceback" not in r.stderr, r.stdout + r.stderr
    assert not (tmp_path / "out" / "demo.fast.mp4").exists()


def clean_env(*dirs):
    env = {"PATH": os.pathsep.join(str(d) for d in dirs)}
    if os.name == "nt":  # Python on Windows cannot start without it
        env["SYSTEMROOT"] = os.environ["SYSTEMROOT"]
    return env


def stub_npx(bin_dir):
    """An npx that records its arguments, so render.py runs without Node."""
    log = bin_dir / "args.txt"
    if os.name == "nt":
        (bin_dir / "npx.bat").write_text(f'@echo %* > "{log}"\r\n')
    else:
        stub = bin_dir / "npx"
        stub.write_text(f'#!/bin/sh\necho "$@" > "{log}"\n')
        stub.chmod(0o755)
    return log


SCRIPTS = ("align.py", "map.py", "outline.py", "validate.py", "render.py", "finalize.py")


def copy_scripts(dst):
    for f in SCRIPTS:
        shutil.copy(HERE / f, dst)


@pytest.mark.parametrize("args,want", [
    (["--frames", "450-451", "--out", "chk.mp4"], "chk.mp4"),
    (["--frames", "450-451"], "demo.frames-450-451.mp4"),
    ([], "demo.mp4"),
    (["--sb", "other"], "demo.sb-other.mp4"),
])
def test_render_frame_range_never_takes_the_full_render_name(tmp_path, args, want):
    copy_scripts(tmp_path)
    for d, body in (("storyboards", '{"scenes":[]}'), ("map", '{"duration":1,"paragraphs":[]}')):
        (tmp_path / d).mkdir()
        (tmp_path / d / "demo.json").write_text(body)
        (tmp_path / d / "other.json").write_text(body)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log = stub_npx(bin_dir)
    sh = shutil.which("sh")
    env = clean_env(bin_dir) if os.name == "nt" else clean_env(bin_dir, Path(sh).parent)
    r = subprocess.run([sys.executable, "render.py", "demo", *args], cwd=tmp_path, env=env, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    out = Path(log.read_text().split(" Episode ", 1)[1].split(" --props=", 1)[0])
    assert (out.parent.name, out.name) == ("out", want)


def make(path, seconds, video):
    src = ["-f", "lavfi", "-i", "color=c=black:s=160x90:r=30", "-c:v", "libx264", "-g", "30", "-pix_fmt", "yuv420p"] if video \
        else ["-f", "lavfi", "-i", "sine=f=440"]
    subprocess.run([FFMPEG, "-y", "-v", "error", *src[:4], "-t", str(seconds), *src[4:], str(path)], check=True)


@needs_ffmpeg
@pytest.mark.parametrize("video_s,ok", [(10, True), (9, False), (11, False), (9.95, True), (9.9, False)])
def test_finalize_checks_video_stream_against_audio(tmp_path, video_s, ok):
    shutil.copy(HERE / "finalize.py", tmp_path)
    (tmp_path / "audio").mkdir()
    (tmp_path / "out").mkdir()
    make(tmp_path / "audio" / "demo.mp3", 10, video=False)
    make(tmp_path / "out" / "demo.mp4", video_s, video=True)
    env = clean_env(Path(FFMPEG).parent, Path(shutil.which("ffprobe")).parent)
    r = subprocess.run([sys.executable, "finalize.py", "--mux"], cwd=tmp_path, env=env, capture_output=True, text=True)
    assert (r.returncode == 0) == ok, r.stdout + r.stderr
    assert (tmp_path / "final" / "demo.mp4").exists() == ok
    assert not (tmp_path / "out" / "demo.fast.mp4").exists()


def test_finalize_names_missing_ffmpeg(tmp_path):
    shutil.copy(HERE / "finalize.py", tmp_path)
    r = subprocess.run([sys.executable, "finalize.py"], cwd=tmp_path, env=clean_env(tmp_path), capture_output=True, text=True)
    assert r.returncode == 1 and "not on PATH" in r.stderr
