"""Write a small state file and prove it actually landed.

Two callers keep a marker file whose entire value is its durability:

  * ``cli/server_ctl.py`` writes ``state/server-stopped-by-user`` so the next
    prompt's health check can tell "the user killed it" from "it died".
  * ``hooks/rag-enforce.py`` writes ``state/last-self-heal`` so a restart that
    cannot fix anything is attempted at most once per cooldown window.

Both fail the same way when a write reports success but leaves the old bytes in
place: an antivirus intercept, a quarantine, or a lazy network / synced folder
write. ``write_text`` raises for none of those, and ``exists()`` or ``stat()``
afterwards still finds the *previous* file, so existence proves nothing.
Comparing the bytes back out is what distinguishes the two.

Scope of the guarantee, stated honestly because overclaiming it is what made
the second copy of this check worthless: the read back goes through the same
page cache the write went into, so this catches a write that was intercepted,
rejected, or silently dropped. It is not an fsync and does not survive a power
loss. Neither caller needs that -- both files only have to outlive the current
process.
"""

from pathlib import Path


def write_durably(path: Path, body: str) -> None:
    """Write *body* to *path*, then read it back and confirm it matches.

    Raises ``OSError`` if the parent directory cannot be created, the write
    fails, the file cannot be read back, or it reads back as anything other
    than *body*. Callers turn that into their own fail-closed behaviour.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    if path.read_text(encoding="utf-8") != body:
        raise OSError(f"{path} read back with different content than was written")
