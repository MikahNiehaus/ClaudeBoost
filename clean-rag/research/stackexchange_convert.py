"""Extracts Posts.xml from each downloaded archive, parses StackExchange's
XML row format, pairs questions with their accepted (or top-scoring)
answer, and writes the result as markdown into knowledge/qa/<site>/.

StackExchange XML dump format (confirmed via the dump's own readme,
present in every archive): Posts.xml is a flat list of <row> elements.
PostTypeId="1" is a question, PostTypeId="2" is an answer. Answers link to
their question via ParentId. AcceptedAnswerId on a question row points at
the accepted answer's Id, when one exists.

Filtering: per the depth-not-breadth intent (this KB should cover
principles and patterns, from fundamentals to advanced, not just whatever
happens to be top-voted), a modest score threshold is applied only to
exclude genuinely low quality/spam content, not to bias toward advanced
topics over basic ones. Both a fundamentals-heavy site (askubuntu) and a
principles-heavy site (softwareengineering) are treated identically by
this filter.
"""

import re
import sys
from pathlib import Path
from xml.etree import ElementTree as ET

import py7zr

RAW_DIR = Path(__file__).resolve().parent.parent / "state" / "stackexchange-raw"
KNOWLEDGE_DIR = Path(__file__).resolve().parent.parent / "knowledge" / "qa"

MIN_SCORE = 5           # excludes low quality/spam, not basic questions
MAX_PAIRS_PER_SITE = 50_000  # bounds embedding time to something tractable
HTML_TAG_RE = re.compile(r"<[^>]+>")


def _strip_html(text: str) -> str:
    """StackExchange Body fields are HTML. Strip tags, keep text and code."""
    text = text.replace("<pre><code>", "\n```\n").replace("</code></pre>", "\n```\n")
    text = text.replace("<code>", "`").replace("</code>", "`")
    text = HTML_TAG_RE.sub("", text)
    text = text.replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&").replace("&quot;", '"').replace("&#39;", "'")
    return text.strip()


def _extract_posts_xml(archive_path: Path, extract_dir: Path) -> Path | None:
    """Extract just Posts.xml from a .7z archive, skip if already extracted."""
    target = extract_dir / "Posts.xml"
    if target.exists():
        return target

    print(f"[extract] {archive_path.name} -> Posts.xml")
    try:
        with py7zr.SevenZipFile(archive_path, mode="r") as archive:
            names = archive.getnames()
            posts_name = next((n for n in names if n.endswith("Posts.xml")), None)
            if not posts_name:
                print(f"[warn] no Posts.xml found in {archive_path.name}")
                return None
            archive.extract(path=extract_dir, targets=[posts_name])
            extracted = extract_dir / posts_name
            if extracted != target:
                extracted.rename(target)
        return target
    except Exception as e:
        print(f"[error] extraction failed for {archive_path.name}: {type(e).__name__}: {e}")
        return None


def _parse_posts(posts_xml: Path) -> tuple[dict, dict]:
    """Single pass over Posts.xml. Returns (questions, answers) keyed by Id.

    Uses iterparse so multi-GB files (stackoverflow's Posts.xml) don't
    need to fit fully in memory at once.
    """
    questions = {}
    answers = {}

    for _, elem in ET.iterparse(str(posts_xml), events=("end",)):
        if elem.tag != "row":
            continue

        post_type = elem.get("PostTypeId")
        score = int(elem.get("Score", "0") or "0")

        if post_type == "1" and score >= MIN_SCORE:  # question
            questions[elem.get("Id")] = {
                "title": elem.get("Title", ""),
                "body": elem.get("Body", ""),
                "tags": elem.get("Tags", ""),
                "score": score,
                "accepted_answer_id": elem.get("AcceptedAnswerId"),
            }
        elif post_type == "2" and score >= MIN_SCORE:  # answer
            answers[elem.get("Id")] = {
                "parent_id": elem.get("ParentId"),
                "body": elem.get("Body", ""),
                "score": score,
            }

        elem.clear()  # free memory, critical for the 21GB stackoverflow file

    return questions, answers


def _best_answer_for(question: dict, question_id: str, answers_by_parent: dict) -> dict | None:
    accepted_id = question.get("accepted_answer_id")
    candidates = answers_by_parent.get(question_id, [])
    if accepted_id:
        for a in candidates:
            if a.get("_id") == accepted_id:
                return a
    if candidates:
        return max(candidates, key=lambda a: a["score"])
    return None


def convert_site(site_slug: str, archive_name: str) -> dict:
    """Full pipeline for one site: extract, parse, pair, write markdown."""
    archive_path = RAW_DIR / archive_name
    if not archive_path.exists():
        print(f"[skip] {site_slug}: archive not downloaded yet")
        return {"site": site_slug, "written": 0, "error": "not downloaded"}

    extract_dir = RAW_DIR / site_slug
    extract_dir.mkdir(parents=True, exist_ok=True)

    posts_xml = _extract_posts_xml(archive_path, extract_dir)
    if not posts_xml:
        return {"site": site_slug, "written": 0, "error": "extraction failed"}

    print(f"[parse] {site_slug}: reading Posts.xml (this can take a while for large files)...")
    questions, answers = _parse_posts(posts_xml)
    print(f"[parse] {site_slug}: {len(questions)} questions, {len(answers)} answers above score {MIN_SCORE}")

    answers_by_parent: dict[str, list] = {}
    for aid, a in answers.items():
        a["_id"] = aid
        answers_by_parent.setdefault(a["parent_id"], []).append(a)

    out_dir = KNOWLEDGE_DIR / site_slug
    out_dir.mkdir(parents=True, exist_ok=True)

    ranked = sorted(questions.items(), key=lambda kv: kv[1]["score"], reverse=True)[:MAX_PAIRS_PER_SITE]

    written = 0
    for qid, q in ranked:
        best = _best_answer_for(q, qid, answers_by_parent)
        if not best:
            continue

        title = _strip_html(q["title"])
        q_body = _strip_html(q["body"])
        a_body = _strip_html(best["body"])
        # Confirmed this dump's actual format is "|tag1|tag2|", not the
        # "<tag1><tag2>" format assumed originally — caught by reading a
        # real converted file, not assumed from the dump's documentation.
        raw_tags = q["tags"]
        if "><" in raw_tags:
            tags = raw_tags.replace("><", ", ").strip("<>")
        else:
            tags = ", ".join(t for t in raw_tags.split("|") if t)

        content = f"""<!-- Source: stackexchange/{site_slug} question {qid} | Score: {q['score']} -->

# {title}

**Tags:** {tags}

## Question

{q_body}

## Answer (score {best['score']})

{a_body}
"""
        (out_dir / f"{qid}.md").write_text(content, encoding="utf-8")
        written += 1

    print(f"[ok] {site_slug}: wrote {written} Q&A markdown files to {out_dir}")
    return {"site": site_slug, "written": written, "error": None}


if __name__ == "__main__":
    from stackexchange_download import SITES

    results = []
    for archive_name, slug in SITES:
        results.append(convert_site(slug, archive_name))

    print("\n=== Summary ===")
    for r in results:
        status = r["error"] or f"{r['written']} files"
        print(f"  {r['site']}: {status}")
