"""Verification prompt templates for the Haiku agent.

The main Claude agent uses these templates to construct the prompt
passed to Agent(model="haiku") for independent proof verification.
"""


VERIFICATION_PROMPT = """CLEAN-RAG VERIFICATION REQUEST

File: {file_path}
Proposed change: {proposed_change}

Architecture context:
{architecture_context}

RAG search results:
{rag_results}

How I know how to make this change:
{justification}

Verify this proof is sufficient. Consider:
1. Do the RAG results actually cover the technology/pattern being used?
2. Is the score high enough to trust the results (>= 0.5)?
3. Does the justification logically connect the research to the edit?
4. Are there gaps where more research would help?

Respond with ONLY one of:
- VERIFIED: [one sentence explaining why the proof is sufficient]
- RESEARCH_MORE: [specific topic that needs more research]
- INSUFFICIENT: [what is missing from the proof]"""


def build_verification_prompt(
    file_path: str,
    proposed_change: str,
    architecture_context: str,
    rag_results: str,
    justification: str,
) -> str:
    """Build the full verification prompt for a Haiku agent spawn."""
    return VERIFICATION_PROMPT.format(
        file_path=file_path,
        proposed_change=proposed_change,
        architecture_context=architecture_context,
        rag_results=rag_results,
        justification=justification,
    )


def format_rag_results(results: list[dict]) -> str:
    """Format RAG search results into a readable string for the verification prompt."""
    if not results:
        return "(no results found)"

    lines = []
    for r in results:
        source_type = r.get("source_type", "unknown")
        score = r.get("score", 0)
        topic = r.get("topic", "")
        file = r.get("file", "")
        content_preview = r.get("content", "")[:500]

        if source_type == "topic":
            lines.append(f"- score: {score:.2f} | topic: {topic} | source: {file}")
        elif source_type == "project":
            line_start = r.get("line_start", 0)
            lines.append(f"- score: {score:.2f} | source: project | file: {file}:{line_start}")
        else:
            lines.append(f"- score: {score:.2f} | source: {source_type} | {file}")

        lines.append(f'  "{content_preview}..."')

    return "\n".join(lines)
