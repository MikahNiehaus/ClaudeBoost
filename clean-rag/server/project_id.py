"""Single source of truth for a project's database directory name.

This used to be computed by hand in six places (server/indexing.py,
server/search.py twice, two hooks, and the graphrag service). When any of
them disagreed the lookup split silently: the code found no directory,
concluded the project had never been indexed, and either returned nothing
or reindexed from scratch. Nothing errored. Everything derives the name
from here now.

Names are `<slug>-<hash>`, e.g. `pantryeasy-98eeaa63`. The slug is there so
a human can tell the directories apart. The hash stays because the slug
alone collides: two checkouts of one project under different parents share
a leaf name, and a collision silently overwrites one project's index with
the other's.

Deliberately dependency free. The server, the standalone hook scripts and
the isolated graphrag venv do not share a site-packages. A slug library
installed in only one of them would produce a different directory name
there, which is the same silent split this module exists to end.

Importing it from a hook follows the pattern already in
hooks/graph-context-inject.py:

    sys.path.insert(0, str(CLEAN_RAG_ROOT))
    from server.project_id import project_dir_name
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

HASH_CHARS = 8              # of a sha256 over the resolved path
LEGACY_HASH_CHARS = 12      # the pre-rename scheme
MAX_SLUG = 40

#: Below this, a parent fragment is noise rather than a hint, so the leaf gets
#: the whole budget instead.
_MIN_PARENT_CHARS = 4

# Windows refuses these as a file or directory name, with or without an
# extension, case insensitively. A project folder called `aux` or `con` is
# short and ordinary enough to actually happen. The superscript forms are
# reserved too, which a hand written character filter reliably misses.
_RESERVED = {
    "con", "prn", "aux", "nul",
    *(f"com{i}" for i in range(1, 10)),
    *(f"lpt{i}" for i in range(1, 10)),
    "com¹", "com²", "com³",
    "lpt¹", "lpt²", "lpt³",
}

_ILLEGAL = re.compile(r'[<>:"/\\|?*\x00-\x1f]')

#: Parent folder names that are containers rather than identity. Prefixing
#: every project with one of these makes the listing longer without making it
#: clearer, which is the opposite of why the slug exists.
_GENERIC_PARENTS = {
    "development", "dev", "src", "source", "code", "projects", "project",
    "repos", "repo", "git", "work", "workspace", "home", "users", "documents",
}


def slugify_name(name: str) -> str:
    """Filesystem safe, lowercase form of one path segment.

    Returns "" when nothing usable survives; the caller must handle that
    rather than creating a directory named after the empty string.
    """
    s = _ILLEGAL.sub("-", name)
    # Dots collapse to hyphens along with whitespace. A reserved name keeps
    # its meaning in front of any extension, so `nul.txt` is still the NUL
    # device and appending a suffix to the end does not save it. Directory
    # names here have no use for an extension, so removing dots entirely
    # retires that whole class instead of trying to special case it.
    s = re.sub(r"[\s_.]+", "-", s.strip().lower())
    s = re.sub(r"-{2,}", "-", s).strip("-")
    if s in _RESERVED:
        s = f"{s}-dir"
    # Windows silently drops a trailing dot or space, so a name ending in
    # one would not round trip.
    return s[:MAX_SLUG].strip("-")


def project_dir_name(project_path) -> str:
    """Directory name under databases/_projects for this project.

    ``<parent>-<leaf>-<hash>``, e.g. ``f-and-b-pwa-nectar-4bea5867``.

    The parent segment is in the name because the leaf alone was genuinely
    ambiguous in practice, not hypothetically: this install has
    ``F and B PWA\\Nectar`` and ``F and B PWA2\\Nectar``, which both slugged to
    ``nectar-<hash>``. Two directories, same readable part, and the only thing
    telling them apart was a hash nobody can map back to a path by eye. That
    defeats the reason the slug exists at all.

    The hash still decides identity. The slug is only ever for humans reading
    a directory listing.
    """
    root = Path(project_path).resolve()
    digest = hashlib.sha256(str(root).encode("utf-8")).hexdigest()[:HASH_CHARS]

    leaf = slugify_name(root.name)
    parent = slugify_name(root.parent.name) if root.parent != root else ""
    # A parent that every project shares is noise, not information. Most
    # projects here live directly under C:\Development, so prefixing all of
    # them with "development-" would make the listing longer and no clearer.
    # The parent earns its place only when it actually distinguishes.
    if parent and parent != leaf and parent not in _GENERIC_PARENTS:
        # Truncate the PARENT, never the combined string. Slicing the join
        # trims from the right, which eats the leaf first: measured, a 59
        # character parent left zero characters of "Nectar" or "AscendMobile",
        # so two projects differed only by hash. That is the exact thing the
        # parent prefix was added to prevent.
        #
        # The leaf is the more identifying half, so it is kept whole and the
        # parent gets whatever room is left.
        room = MAX_SLUG - len(leaf) - 1  # -1 for the joining hyphen
        # Strip BEFORE measuring, not after. An internal hyphen landing exactly
        # on the truncation boundary is removed by strip(), so a fragment that
        # cleared the budget check could still reach the slug three characters
        # long, below the threshold that says a fragment this short is noise.
        fragment = parent[:room].strip("-") if room > 0 else ""
        if len(fragment) >= _MIN_PARENT_CHARS:
            slug = f"{fragment}-{leaf}"
        else:
            # No room for a parent worth reading. The hash still disambiguates.
            slug = leaf[:MAX_SLUG]
    else:
        slug = leaf[:MAX_SLUG]
    slug = slug.strip("-")
    return f"{slug}-{digest}" if slug else digest


def leaf_only_dir_name(project_path) -> str:
    """The previous scheme: ``<leaf>-<hash>``. Fallback for existing indexes."""
    root = Path(project_path).resolve()
    digest = hashlib.sha256(str(root).encode("utf-8")).hexdigest()[:HASH_CHARS]
    slug = slugify_name(root.name)
    return f"{slug}-{digest}" if slug else digest


def legacy_project_dir_name(project_path) -> str:
    """The pre-rename name: a bare 12 char hash. Migration and fallback only."""
    root = Path(project_path).resolve()
    return hashlib.sha256(str(root).encode("utf-8")).hexdigest()[:LEGACY_HASH_CHARS]


def resolve_project_dir(projects_root, project_path) -> Path:
    """Where this project's data actually is.

    Prefers the current scheme but returns the legacy hash directory when
    that is what exists on disk. Without this, the code change and the
    directory migration would have to land in the same instant or every
    lookup would miss and silently reindex. An install that pulls the code
    and has not migrated keeps working.
    """
    projects_root = Path(projects_root)
    current = projects_root / project_dir_name(project_path)
    if current.exists():
        return current
    # Three schemes have existed. Each new one has to keep finding the older
    # directories or the lookup misses, the code decides the project was never
    # indexed, and it silently rebuilds from scratch. That is hours per project
    # here, so the fallbacks stay until the directories are actually migrated.
    for older in (leaf_only_dir_name, legacy_project_dir_name):
        candidate = projects_root / older(project_path)
        if candidate.exists():
            return candidate
    return current
