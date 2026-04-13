#!/usr/bin/env python3
"""Render a self-contained visualize.html from graph.json + template + CSS."""

import json
import sys
from pathlib import Path


def render(graph_path: str, output_path: str) -> None:
    viewer_dir = Path(__file__).parent
    template = (viewer_dir / "index.template.html").read_text(encoding="utf-8")
    css = (viewer_dir / "visualize.css").read_text(encoding="utf-8")

    graph_text = Path(graph_path).read_text(encoding="utf-8")
    graph_data = json.loads(graph_text)

    title = graph_data.get("title", graph_data.get("project", "Architecture"))

    html = template
    html = html.replace("__CSS_PLACEHOLDER__", css)
    html = html.replace("__TITLE_PLACEHOLDER__", title)
    html = html.replace('"__DATA_PLACEHOLDER__"', graph_text)

    Path(output_path).write_text(html, encoding="utf-8")
    print(f"Rendered: {output_path} ({len(html):,} bytes)")


def main() -> None:
    if len(sys.argv) < 3:
        print("Usage: python render.py <graph.json> <output.html>", file=sys.stderr)
        sys.exit(1)
    render(sys.argv[1], sys.argv[2])


if __name__ == "__main__":
    main()
