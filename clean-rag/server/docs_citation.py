"""Citation extraction for official documents.

Every chunk stored by the docs feature must carry a falsifiable citation: a
real, checkable pointer (jurisdiction, citation string, source URL) that lets
a human verify a search result in seconds instead of trusting a similarity
score. That's the hard requirement clean-rag/CLAUDE.md's "Why the KB is gone"
section imposes on any persistent document corpus in this project -- a chunk
with no falsifiable citation is exactly the failure mode that got the old
topic KB removed.

The primary citation is always deterministic: the source list's own
citation_prefix plus the chunk's own heading, as found by docs_chunker. That
alone is a real, checkable citation, no NLP needed.

eyecite is enrichment only, never a replacement for the primary citation.
Confirmed by actually running it against real eCFR section text, not
assumed: the first citation eyecite finds in a section's body is usually an
incidental reference to some OTHER law mentioned in passing (e.g. a
definitions section that name drops "Pub. L. 104-191" mid paragraph), not
the section's own self citation. Treating that as the chunk's primary
citation would mislabel a chunk about one section as being about a
different one entirely. So eyecite results are surfaced as a separate
`related_citations` list, additive metadata, and the primary citation never
depends on eyecite being installed, correct, or even present.
"""

import logging
import re

logger = logging.getLogger(__name__)

try:
    from eyecite import get_citations
    from eyecite.models import UnknownCitation
    HAS_EYECITE = True
except ImportError:
    HAS_EYECITE = False
    logger.warning("eyecite not installed -- related_citations enrichment disabled")

_TAG_RE = re.compile(r"<[^>]+>")


def extract_citation(heading: str, citation_prefix: str) -> str:
    """Build the primary, checkable citation string for a chunk.

    Args:
        heading: The chunk's own section heading, as found by docs_chunker
            (e.g. "Sec. 392.001. DEFINITIONS." or "(?!)" sentinel sources'
            constant "Preamble").
        citation_prefix: The source list entry's jurisdiction/code prefix
            (e.g. "Tex. Fin. Code" or "45 CFR 160.103").
    """
    # "Preamble" is docs_chunker's bucket name for text before the first
    # matched heading. For a source that's already scoped to one section
    # before it ever reaches the chunker (a single section eCFR fetch, for
    # example), nothing in the text will ever match the heading pattern, so
    # every chunk lands in that bucket. Appending the literal word "Preamble"
    # to a citation would be noise, not information, so it's dropped here;
    # citation_prefix alone is still a real, checkable citation in that case.
    if heading in ("Preamble", ""):
        return citation_prefix.strip()
    return f"{citation_prefix} {heading}".strip()


def extract_related_citations(chunk_text: str, limit: int = 5) -> list[str]:
    """Find other real citations mentioned inside a chunk's own text.

    Additive enrichment only, never the primary citation (see module
    docstring for why). Empty list if eyecite is unavailable, finds nothing,
    or every match is a low confidence UnknownCitation.
    """
    if not HAS_EYECITE or not chunk_text:
        return []

    # eyecite is built for prose, not markup: an unstripped XML/HTML tag
    # (e.g. "<HEAD>") reads to it as citation shaped debris and comes back as
    # a low confidence UnknownCitation. Strip tags first.
    plain_text = _TAG_RE.sub(" ", chunk_text[:2000])
    try:
        found = [c for c in get_citations(plain_text) if not isinstance(c, UnknownCitation)]
    except Exception as e:
        logger.debug("eyecite parse failed, no related citations: %s", e)
        return []

    # corrected_citation() is eyecite's own clean formatted string; str() on
    # a citation object is its debug repr, confirmed by direct testing, not
    # something to ever show a user.
    return [c.corrected_citation() for c in found[:limit]]


def citation_from_ecfr_div(n_attr: str, node_attr: str, title: int) -> str:
    """Build a citation string from an eCFR XML DIV element's N/NODE attributes.

    N is the human-readable citation number (e.g. "160.103"); NODE is the
    internal structured path. Per usgpo/bulk-data's ECFR-XML-User-Guide.md,
    DIV8 TYPE="SECTION" elements carry these directly -- this is reading a
    citation the source already stamped, not inferring one.
    """
    return f"{title} CFR {n_attr}".strip()


_ECFR_SECTION_DIV_RE = re.compile(
    r'<DIV8\s[^>]*N="([^"]+)"[^>]*TYPE="SECTION"', re.IGNORECASE,
)


def section_numbers_in_ecfr_xml(xml_text: str) -> list[str]:
    """Return every SECTION citation number (the N attribute) found in eCFR XML.

    A lightweight regex scan rather than a full XML parse: eCFR bulk XML can
    be large, and the N attribute is the only thing needed here, not a DOM.
    """
    return _ECFR_SECTION_DIV_RE.findall(xml_text)
