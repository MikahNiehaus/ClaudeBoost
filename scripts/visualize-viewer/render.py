#!/usr/bin/env python3
"""Render a self-contained visualize.html from graph.json + template + CSS.

Optionally embeds narration audio + timing if narration.mp3 and
narration-timing.json exist in the same directory as graph.json.
"""

import base64
import json
import mimetypes
import sys
from pathlib import Path


def embed_image(path: str, base_dir: Path) -> str:
    """Return a data URI for local image paths; pass through URLs and data URIs."""
    if path.startswith(("http://", "https://", "data:")):
        return path
    img_path = Path(path)
    if not img_path.is_absolute():
        img_path = base_dir / img_path
    if not img_path.exists():
        return path  # Browser will show broken-image placeholder
    mime = mimetypes.guess_type(str(img_path))[0] or "image/png"
    b64 = base64.b64encode(img_path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{b64}"


def embed_images_in(value, base_dir: Path):
    """Recursively walk graph data and embed any local image paths."""
    if isinstance(value, dict):
        result = {}
        for k, v in value.items():
            if k == "image" and isinstance(v, str):
                result[k] = embed_image(v, base_dir)
            else:
                result[k] = embed_images_in(v, base_dir)
        return result
    if isinstance(value, list):
        return [embed_images_in(item, base_dir) for item in value]
    return value


def render(graph_path: str, output_path: str) -> None:
    viewer_dir = Path(__file__).parent
    template = (viewer_dir / "index.template.html").read_text(encoding="utf-8")
    css = (viewer_dir / "visualize.css").read_text(encoding="utf-8")

    graph_file = Path(graph_path)
    graph_data = json.loads(graph_file.read_text(encoding="utf-8"))

    # Embed local images so the HTML is fully self-contained
    graph_data = embed_images_in(graph_data, graph_file.parent)
    graph_text = json.dumps(graph_data, ensure_ascii=False)

    title = graph_data.get("title", graph_data.get("project", "Architecture"))

    # Optionally embed narration (narration.mp3 + narration-timing.json)
    narration_json = "null"
    mp3_path = graph_file.parent / "narration.mp3"
    timing_path = graph_file.parent / "narration-timing.json"
    if mp3_path.exists() and timing_path.exists():
        mp3_b64 = base64.b64encode(mp3_path.read_bytes()).decode("ascii")
        timing_data = json.loads(timing_path.read_text(encoding="utf-8"))
        narration_obj = {
            "audio": f"data:audio/mpeg;base64,{mp3_b64}",
            "timing": timing_data,
        }
        narration_json = json.dumps(narration_obj, ensure_ascii=False)
        print(f"Narration embedded: {mp3_path.stat().st_size:,} bytes")

    html = template
    html = html.replace("__CSS_PLACEHOLDER__", css)
    html = html.replace("__TITLE_PLACEHOLDER__", title)
    html = html.replace('"__DATA_PLACEHOLDER__"', graph_text)
    html = html.replace('"__NARRATION_PLACEHOLDER__"', narration_json)

    Path(output_path).write_text(html, encoding="utf-8")
    print(f"Rendered: {output_path} ({len(html):,} bytes)")


def main() -> None:
    if len(sys.argv) < 3:
        print("Usage: python render.py <graph.json> <output.html>", file=sys.stderr)
        sys.exit(1)
    render(sys.argv[1], sys.argv[2])


if __name__ == "__main__":
    main()
