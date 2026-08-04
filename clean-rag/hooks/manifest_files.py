"""Dependency manifests, gated by exact filename since they carry no unique suffix.

research-gate.py, research-gate-bash.py, verifier-gate.py, and turn_edits.py each
key "is this a code file" off a suffix set. package.json, requirements.txt, and
their siblings are .json/.txt/.toml, so that suffix check waves them straight
through: an edit that deletes a dependency line was never researched or reviewed,
because nothing recognized it as a change worth gating (observed: a real turn
removed a dependency, unresearched, this way). Lock files are deliberately left
out, they are normally machine written by an install/uninstall command, not hand
edited, and gating them would fire on routine installs rather than the actual
deletion this exists to catch.
"""

from pathlib import Path

MANIFEST_FILES = frozenset({
    "package.json", "requirements.txt", "pyproject.toml", "Pipfile",
    "Cargo.toml", "go.mod", "Gemfile", "composer.json",
    "build.gradle", "build.gradle.kts", "build.sbt", "pom.xml",
})


def is_gated_file(path, code_extensions) -> bool:
    """True if path is either a recognized code suffix or a dependency manifest."""
    p = Path(path)
    return p.suffix.lower() in code_extensions or p.name in MANIFEST_FILES
