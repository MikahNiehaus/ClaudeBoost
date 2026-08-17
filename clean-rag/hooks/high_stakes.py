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
    # Not a surface like the others: a tampering signal. The rest of this table
    # answers "where would a passing test fail to prove the property". This one
    # answers "was the test made to pass instead of the code". It belongs here
    # because the consumer is the same (the verifier nudge names the category, so
    # bad-cop is pointed at it) and because a silenced check is the one defect
    # that makes every other category's evidence worthless: the suite goes green
    # either way.
    #
    # Needles are deliberately specific. "skip(" and "except exception:" were
    # both considered and rejected: the first hits ordinary parser and pagination
    # code, the second hits hundreds of legitimate lines in this repo alone. A
    # category that fires on every diff gets the whole gate ignored, which is the
    # over trigger failure named at the top of this file.
    # The TypeScript escape hatches carry their trailing punctuation on purpose.
    # A bare "as any" needle matches ordinary prose ("such as anything", "as any
    # of the callers"), and because this category deliberately bypasses the
    # comment only skip below, a comment containing that phrase would flag. The
    # cast shapes are what the defect actually looks like.
    "test-weakening": (
        "mark.skip", "mark.xfail", "xfail", "unittest.skip", "@skip",
        "type: ignore", "# noqa", "eslint-disable", "@ts-ignore",
        "@ts-expect-error", "pylint: disable", "suppresswarnings",
        "assert true", "@ignore", "#[ignore]", "skip_reason",
        "as any;", "as any)", "as any,", "as any]", "as unknown as", "<any>",
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
        # A comment that merely names a surface ("money, SQL, subprocess") is not
        # high stakes code, and matching it is the over trigger that gets a gate
        # ignored. Code with a trailing comment still matches, since the line does
        # not start with a comment marker.
        #
        # test-weakening is exempt from that skip: for this one category the
        # comment IS the defect, not a mention of it. `# type: ignore`,
        # `# pylint: disable=...` and `// eslint-disable-next-line` are the
        # silencing mechanism itself, and they are frequently the whole line.
        # Skipping comment only lines here would miss the most common shape.
        is_comment_only = stripped.startswith(("#", "//", "*", '"""', "'''", "/*"))
        low = raw.lower()
        for cat, needles in _KEYWORDS.items():
            if is_comment_only and cat != "test-weakening":
                continue
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

    # A silenced test is a tampering signal, not a surface.
    h = scan_diff(["@pytest.mark.skip(reason='flaky')"], ["tests/test_pay.py"])
    assert "test-weakening" in h, h

    # A type checker silenced on a trailing comment.
    h = scan_diff(["    total = a + b  # type: ignore"], ["src/calc.py"])
    assert "test-weakening" in h, h

    # A lint disable that IS the whole line must trip, even though the general
    # comment only skip would otherwise drop it. This is the case the exemption
    # exists for.
    h = scan_diff(["# pylint: disable=broad-except"], ["src/util.py"])
    assert "test-weakening" in h, h
    h = scan_diff(["// eslint-disable-next-line no-unused-vars"], ["src/a.ts"])
    assert "test-weakening" in h, h

    # A neutered assertion.
    h = scan_diff(["    assert True  # was: assert balance >= 0"], ["tests/t.py"])
    assert "test-weakening" in h, h

    # Ordinary code must NOT trip test-weakening. These were the rejected
    # needles: a pagination skip and a broad except are both normal.
    h = scan_diff(["    rows = q.skip(offset).limit(size)"], ["src/repo.py"])
    assert "test-weakening" not in h, h
    h = scan_diff(["    except Exception as exc:"], ["src/util.py"])
    assert "test-weakening" not in h, h

    # A comment merely discussing the concept must not trip either.
    h = scan_diff(["# never weaken a failing test to get green"], ["docs/x.py"])
    assert h == {}, h

    print("HIGH_STAKES OK")
