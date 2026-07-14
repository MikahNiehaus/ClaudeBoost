"""Deterministic high stakes labeler for the verifier gate.

Surfaces where a passing test especially fails to prove the property: auth, money,
SQL, subprocess boundaries, and concurrency. This flags, cheaply and without an
LLM, which of those a diff touched.

It no longer decides WHETHER to run the verifier. The verifier now fires on any
code change (unless the turn was /ps), so this is a labeler: its hits tell the
nudge which risk to name so the reviewer is pointed at the sharpest thing. An empty
result no longer means "skip the review", just "no named high stakes surface, do a
general correctness pass".

Detection is deterministic on purpose. A keyword match has no judgment behind it,
but that is fine here: it only labels, and the judgment happens in the verifier,
not here. Never put an LLM in the detection path, that is the mechanical query
mistake the topic knowledge base died of.

Two failure modes to tune against, both real: over trigger (flag every file, the
gate gets ignored) and under trigger (miss the one risky line). So the keyword sets
are broad where a miss is a security bug (sql, auth, subprocess) and narrow where a
routine file would otherwise trip it. Plain async/await is normal control flow, not
a race, so concurrency keys on the actual hazard: shared state primitives, threads,
processes.

scan_diff takes the ADDED lines of a diff (the risk is in what was added, not the
whole file) plus the changed file paths, and returns {category: [evidence]}.
"""

# Substrings checked against each added line, lowercased.
_KEYWORDS = {
    "sql": (
        "execute(", "executemany(", "cursor.", ".query(", "text(",
        "select ", "insert into", "update ", "delete from", " where ",
    ),
    "auth": (
        "password", "passwd", "token", "secret", "api_key", "apikey",
        "session", "jwt", "oauth", "login", "authenticate", "authorize",
        "permission", "role", "is_admin", "verify_signature", "hmac",
    ),
    "subprocess": (
        "subprocess", "os.system", "os.popen", "eval(", "exec(",
        "shell=true", "pty.spawn", "child_process",
    ),
    "concurrency": (
        "threading.", "thread(", "multiprocessing", "semaphore(", "lock(",
        ".acquire(", "shared_state", "race",
    ),
    "money": (
        "balance", "payment", "charge(", "refund", "transfer(", "transaction",
        "invoice", "wallet", "stripe", "paypal",
    ),
}

# A path whose name matches one of these is treated as touching that category even
# if the added lines did not, since the file is that concern. Kept high signal to
# avoid over triggering on common names.
_PATH_HINTS = {
    "sql": ("migration", "schema"),
    "auth": ("auth", "login", "session", "permission", "security"),
    "subprocess": ("shell", "command_runner"),
    "concurrency": ("worker", "scheduler"),
    "money": ("payment", "billing", "checkout", "wallet", "invoice", "ledger"),
}

_CAP = 5  # evidence lines per category, so the nudge stays short


def scan_diff(added_lines, changed_paths):
    """Return {category: [evidence]} for the high stakes surfaces a diff touched.

    added_lines: the '+' lines of the diff, with the leading '+' already stripped.
    changed_paths: the file paths the diff changed.
    An empty dict means nothing high stakes, so the verifier is not worth spending.
    """
    hits: dict[str, list[str]] = {}

    for raw in added_lines or []:
        stripped = raw.strip()
        # Skip a comment only line. A comment that merely names a surface ("money,
        # SQL, subprocess") is not high stakes code, and matching it is the over
        # trigger that gets a gate ignored. Code with a trailing comment still
        # matches, since the line does not start with a comment marker.
        if stripped.startswith(("#", "//", "*", '"""', "'''", "/*")):
            continue
        low = raw.lower()
        for cat, needles in _KEYWORDS.items():
            if any(n in low for n in needles):
                bucket = hits.setdefault(cat, [])
                ev = raw.strip()[:200]
                if len(bucket) < _CAP and ev not in bucket:
                    bucket.append(ev)

    for path in changed_paths or []:
        low = path.lower()
        for cat, hints in _PATH_HINTS.items():
            if any(h in low for h in hints):
                bucket = hits.setdefault(cat, [])
                marker = f"(path) {path}"
                if len(bucket) < _CAP and marker not in bucket:
                    bucket.append(marker)

    return hits


if __name__ == "__main__":
    # SQL built by string formatting is the textbook injection.
    h = scan_diff(['    cur.execute("select * from users where id=%s" % uid)'], ["db.py"])
    assert "sql" in h, h

    # Token comparison is an auth surface.
    h = scan_diff(["    if token == expected_token:"], ["src/auth/login.py"])
    assert "auth" in h, h

    # shell=True with a built command.
    h = scan_diff(["    subprocess.run(cmd, shell=True)"], ["run.py"])
    assert "subprocess" in h, h

    # A real concurrency primitive, not plain async.
    h = scan_diff(["    with self._lock():"], ["worker.py"])
    assert "concurrency" in h, h

    # Money path.
    h = scan_diff(["    balance -= charged"], ["billing/charge.py"])
    assert "money" in h, h

    # Plain async control flow must NOT trip concurrency (the over trigger trap).
    h = scan_diff(["async def fetch(url):", "    return await client.get(url)"], ["src/net.py"])
    assert h == {}, h

    # A benign pure function trips nothing.
    h = scan_diff(["def add(a, b):", "    return a + b"], ["src/mathutil.py"])
    assert h == {}, h

    # A comment that merely names the surfaces must NOT trip (the over trigger fix).
    h = scan_diff(["# handles auth, money, SQL, subprocess, concurrency"], ["src/util.py"])
    assert h == {}, h

    # But real code with a trailing comment still trips.
    h = scan_diff(["    subprocess.run(cmd, shell=True)  # run it"], ["src/run.py"])
    assert "subprocess" in h, h

    print("HIGH_STAKES OK")
