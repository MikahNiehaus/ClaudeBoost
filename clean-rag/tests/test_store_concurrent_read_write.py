"""One sqlite connection, many threads: every access point must be serialized.

The incident. On 2026-09-17 a live `/search` returned 500 with
`sqlite3.InterfaceError: bad parameter or other API misuse`, raised from
`store.py`'s existence check:

    if not self._conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (vec,),
    ).fetchone():

The bind was innocent: `vec` is always the string `vec_<name>`. The server log
showed several `/search` and `/status` calls overlapping at that instant, and a
failed search falls through to a DuckDuckGo fallback, so the 500 also cost a
silent three second detour.

The cause is not a bad parameter. `_open_connection` opens with
`check_same_thread=False`, which turns off Python's own guard and hands all
coordination to the caller. Every write path took `write_lock`; no read path
took anything. From CPython 3.12 one `Connection` driven from two threads can
raise exactly this error, return short rows, or read inside another thread's
transaction, because one thread resets or finalizes a statement while another
is still stepping it.

WAL mode does not help and neither does sqlite-vec. WAL governs concurrency
between separate connections to a file; this is two threads sharing one
connection object. `_open_connection` already sets WAL, and the bug happened
anyway.

Per-thread connections are NOT the fix here, and `_CachedConnection`'s own
docstring says why: this project already tried two connections to one path and
hit a worse bug, two writers racing `_ensure_vec_table`'s check-then-create
until the loser's whole `add_chunks` failed with "table already exists". One
connection per path is load bearing.

So the fix is the one the async sqlite bridges use: funnel every access through
a single serialization point. These tests pin that, in three directions: the
race itself, a per-method lock probe, and a source scan that needs no update
when a method is added.
"""
from __future__ import annotations

import ast
import random
import sys
import threading
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from server.store import Chunk, ChromaStore  # noqa: E402

STORE_SOURCE = Path(__file__).resolve().parents[1] / "server" / "store.py"

DIM = 8
COLLECTION = "codebase"


def _chunk(n: int) -> Chunk:
    return Chunk(
        id=f"chunk-{n}-{random.randint(0, 1 << 30)}",
        content=f"content {n}",
        embedding=[random.random() for _ in range(DIM)],
        metadata={"source_file": f"f{n % 5}.py"},
    )


@pytest.fixture
def store(tmp_path):
    """A real store on a scratch directory, never the project's own index."""
    s = ChromaStore(str(tmp_path / "idx"))
    s.create_collection(COLLECTION)
    s.add_chunks(COLLECTION, [_chunk(i) for i in range(20)])
    yield s


def _hammer(store, seconds_of_work: int, errors: list, stop: threading.Event):
    """Readers and writers racing on the one shared connection."""
    def reader():
        try:
            while not stop.is_set():
                store.search(COLLECTION, [random.random() for _ in range(DIM)], limit=3)
                store.count(COLLECTION)
                store.count_sources(COLLECTION)
                store.collection_exists(COLLECTION)
                store.list_sources(COLLECTION)
                store.sample_dimension(COLLECTION)
                store.get_by_source(COLLECTION, "f0.py", limit=1)
                store.vacuum_if_needed()
        except Exception as exc:  # noqa: BLE001 - the point is to catch anything
            errors.append(("reader", type(exc).__name__, str(exc)))
            stop.set()

    def writer():
        try:
            n = 0
            while not stop.is_set():
                store.add_chunks(COLLECTION, [_chunk(n)])
                n += 1
        except Exception as exc:  # noqa: BLE001
            errors.append(("writer", type(exc).__name__, str(exc)))
            stop.set()

    threads = [threading.Thread(target=reader, daemon=True) for _ in range(6)]
    threads += [threading.Thread(target=writer, daemon=True) for _ in range(4)]
    for t in threads:
        t.start()
    stop.wait(seconds_of_work)
    stop.set()
    for t in threads:
        t.join(timeout=10)


def test_concurrent_reads_and_writes_raise_nothing(store):
    """The reproduction. Fails on an unlocked read path, passes once serialized.

    Ten threads is enough to land two calls on the connection at the same
    instant within a couple of seconds. It is a race, so this is a
    probabilistic reproduction rather than a deterministic one: it was observed
    failing reliably in seconds before the fix, and the value of keeping it is
    that a future unlocked read path gets caught here rather than in
    production.
    """
    errors: list = []
    _hammer(store, seconds_of_work=3, errors=errors, stop=threading.Event())
    assert not errors, (
        "concurrent access to the shared sqlite connection raised:\n"
        + "\n".join(f"  {where}: {name}: {msg}" for where, name, msg in errors)
    )


def test_every_public_read_holds_the_same_lock_as_the_writes(store):
    """The structural half, which does not depend on winning a race.

    The reproduction above can pass by luck on a quiet machine. This cannot: it
    asserts that each read method actually acquires the handle's lock, by
    holding that lock from another thread and confirming the call blocks.
    """
    reads = [
        ("search", lambda: store.search(COLLECTION, [0.1] * DIM, limit=1)),
        ("count", lambda: store.count(COLLECTION)),
        ("count_sources", lambda: store.count_sources(COLLECTION)),
        ("list_sources", lambda: store.list_sources(COLLECTION)),
        ("collection_exists", lambda: store.collection_exists(COLLECTION)),
        ("sample_dimension", lambda: store.sample_dimension(COLLECTION)),
        ("get_by_source", lambda: store.get_by_source(COLLECTION, "f0.py", limit=1)),
        # Its freelist gate is a read on the shared handle like any other.
        ("vacuum_if_needed", lambda: store.vacuum_if_needed()),
    ]

    unguarded = []
    for name, call in reads:
        finished = threading.Event()

        def run():
            call()
            finished.set()

        # Hold the lock, then confirm the read cannot complete while it is held.
        with store._write_lock:
            t = threading.Thread(target=run, daemon=True)
            t.start()
            completed_while_locked = finished.wait(0.4)
        t.join(timeout=10)

        if completed_while_locked:
            unguarded.append(name)

    assert not unguarded, (
        "these read methods ran while the connection's lock was held by another "
        f"thread, so they are not serialized against writes: {unguarded}"
    )


def _is_attr(node, name: str) -> bool:
    """True for the expression ``self.<name>``."""
    return (
        isinstance(node, ast.Attribute)
        and node.attr == name
        and isinstance(node.value, ast.Name)
        and node.value.id == "self"
    )


def _parent_map(tree: ast.AST) -> dict:
    return {
        child: node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)
    }


def _enclosing_function(node, parents):
    while node is not None:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return node
        node = parents.get(node)
    return None


def _invoked_in_place(lam, parents) -> bool:
    """True for ``(lambda: ...)()``, whose body runs before the call returns."""
    parent = parents.get(lam)
    return isinstance(parent, ast.Call) and parent.func is lam


def _runs_in_place(node, parents) -> bool:
    """False when a deferred ``lambda`` sits between ``node`` and its own ``def``.

    A method that inherits a proved claim only passes it on to what actually
    runs while it runs.
    """
    parent = parents.get(node)
    while parent is not None and not isinstance(parent, (ast.FunctionDef, ast.AsyncFunctionDef)):
        if isinstance(parent, ast.Lambda) and not _invoked_in_place(parent, parents):
            return False
        parent = parents.get(parent)
    return True


def _under_write_lock(node, parents) -> bool:
    """True when ``node`` sits lexically inside ``with self._write_lock:``.

    The walk stops at the enclosing ``def``, and at a ``lambda`` unless that
    lambda is invoked in place. Writing a callable inside the lock says nothing
    about when it runs, so a stored lambda, one handed to a thread, or a nested
    function is judged on its own and reads as unguarded. Error Prone draws the
    line in the same place for ``@GuardedBy``: its ``HeldLockAnalyzer`` does not
    descend into a lambda, and carries the held locks in only for an allowlist
    of callers known to invoke on the calling thread.

    A closure that only ever runs inside the lock is flagged anyway. That is the
    accepted cost, as is refusing ``acquire()``/``release()``, which pins the
    exception safe ``with`` form.
    """
    child = node
    parent = parents.get(node)
    while parent is not None:
        if isinstance(parent, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return False
        if isinstance(parent, ast.Lambda) and not _invoked_in_place(parent, parents):
            return False
        if (
            isinstance(parent, ast.With)
            and any(_is_attr(i.context_expr, "_write_lock") for i in parent.items)
            and any(child is stmt or child in ast.walk(stmt) for stmt in parent.body)
        ):
            return True
        child, parent = parent, parents.get(parent)
    return False


def _assignment_target_ids(tree: ast.AST) -> set[int]:
    """Nodes being assigned to, which store a handle rather than drive one."""
    ids = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            targets = node.targets
        elif isinstance(node, (ast.AnnAssign, ast.AugAssign, ast.For, ast.AsyncFor)):
            targets = [node.target]
        else:
            continue
        for target in targets:
            ids.update(id(n) for n in ast.walk(target))
    return ids


def _is_none_check(parent, node) -> bool:
    """True for ``self._conn is None`` and ``is not None``, which drive nothing."""
    return (
        isinstance(parent, ast.Compare)
        and parent.left is node
        and all(isinstance(op, (ast.Is, ast.IsNot)) for op in parent.ops)
        and all(
            isinstance(c, ast.Constant) and c.value is None for c in parent.comparators
        )
    )


def _classify_conn_refs(tree, parents) -> tuple[list, list]:
    """Split every ``self._conn`` reference into uses of the handle and escapes.

    A use reads the attribute without copying it: a member access such as
    ``self._conn.execute(...)``, or ``with self._conn:``. Those need the lock.
    A ``None`` check drives no statement, and assigning to the attribute stores
    a handle rather than using one, so neither is a use.

    Anything else is an escape: a local alias, a walrus, an argument, a return.
    Escapes are reported wherever they sit, lock or no lock, because the copy
    can be driven from anywhere afterwards and nothing here can follow it.
    Error Prone's ``@GuardedBy`` documents exactly this hole as a limitation it
    does not close, that the analysis "does not track aliasing, so it is
    possible to circumvent the safety it provides by copying references to
    guarded members". Refusing the copy is decidable; chasing it is not.
    """
    targets = _assignment_target_ids(tree)
    uses, escapes = [], []
    for node in ast.walk(tree):
        if not _is_attr(node, "_conn") or id(node) in targets:
            continue
        parent = parents.get(node)
        if isinstance(parent, ast.Attribute):
            uses.append(parent)
        elif isinstance(parent, ast.withitem) and parent.context_expr is node:
            uses.append(node)
        elif not _is_none_check(parent, node):
            escapes.append(node)
    return uses, escapes


def _verified_caller_locked(tree, parents) -> tuple[set[str], set[str]]:
    """Which methods claim the caller holds the lock, and which of those hold up.

    A docstring is a claim, so it gets checked against the real call sites in
    this module: every one runs under the lock, or sits inside another claiming
    method that passed the same test. Nothing is believed until it is proved,
    which is what stops a ring of methods vouching for each other, and a claim
    with no call site here cannot be proved at all so it fails.

    Only a call proves anything. A bare ``self._helper`` reference is a copy of
    the bound method, run at a moment only its recipient decides, so the claim is
    refused rather than judged at the line the copy was written on. That is the
    same refusal ``_classify_conn_refs`` makes for a copy of the handle.
    """
    claimed = {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and "under self._write_lock" in (ast.get_docstring(node) or "")
    }
    sites: dict[str, list] = {name: [] for name in claimed}
    escaped: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Attribute) or node.attr not in claimed:
            continue
        if not (isinstance(node.value, ast.Name) and node.value.id == "self"):
            continue
        parent = parents.get(node)
        if isinstance(parent, ast.Call) and parent.func is node:
            sites[node.attr].append(parent)
        else:
            escaped.add(node.attr)

    verified: set[str] = set()
    while True:
        proved = {
            name
            for name, calls in sites.items()
            if name not in verified
            and name not in escaped
            and calls
            and all(
                _under_write_lock(call, parents)
                or (
                    _runs_in_place(call, parents)
                    and getattr(_enclosing_function(call, parents), "name", None) in verified
                )
                for call in calls
            )
        }
        if not proved:
            return claimed, verified
        verified |= proved


def _unguarded_conn_sites(tree: ast.AST) -> list[str]:
    """Names every ``self._conn`` reference this scan cannot prove is serialized.

    Two ways a reference passes. It runs lexically under
    ``with self._write_lock:``, or it sits in a method whose docstring states
    the caller holds the lock and whose call sites were checked and found to do
    so, the contract ``_ensure_vec_table`` documents. A third way used to exist,
    trusting that docstring on its own, which let a method exempt itself while
    every caller ignored it.
    """
    parents = _parent_map(tree)
    claimed, verified = _verified_caller_locked(tree, parents)
    uses, escapes = _classify_conn_refs(tree, parents)

    def where(node) -> str:
        func = _enclosing_function(node, parents)
        return func.name if func else "<module>"

    found = [
        (node.lineno, f"{where(node)} at line {node.lineno} (self._conn copied out)")
        for node in escapes
    ]
    for node in uses:
        name = where(node)
        if name in claimed and name in verified:
            continue
        if not _under_write_lock(node, parents):
            found.append((node.lineno, f"{name} at line {node.lineno}"))
    return [text for _, text in sorted(found)]


def test_no_statement_runs_on_the_shared_handle_outside_the_lock():
    """The scan that survives a new method being added.

    The probe above enumerates methods by hand, so a method written next year
    is absent from it and goes unguarded silently. That is how
    `vacuum_if_needed` kept two unlocked PRAGMA reads while the class docstring
    claimed every access took the lock. This reads `store.py` and finds the
    access points itself.
    """
    unguarded = _unguarded_conn_sites(ast.parse(STORE_SOURCE.read_text(encoding="utf-8")))
    assert not unguarded, (
        "these run a statement on the shared connection without holding its "
        "lock, and without documenting that the caller holds it: "
        + ", ".join(unguarded)
    )


def test_the_scan_catches_an_unlocked_access():
    """Proof the scan bites, rather than passing on whatever it is handed."""
    source = (
        "class S:\n"
        "    def locked(self):\n"
        "        with self._write_lock:\n"
        "            self._conn.execute('SELECT 1')\n"
        "    def unlocked(self):\n"
        "        self._conn.execute('PRAGMA freelist_count')\n"
        "    def caller_holds_it(self):\n"
        "        '''Must be called under self._write_lock.'''\n"
        "        self._conn.execute('SELECT 2')\n"
        "    def honest_caller(self):\n"
        "        with self._write_lock:\n"
        "            self.caller_holds_it()\n"
        "    def only_a_none_check(self):\n"
        "        if self._conn is None:\n"
        "            return False\n"
    )
    found = _unguarded_conn_sites(ast.parse(source))
    assert found == ["unlocked at line 6"], found


@pytest.mark.parametrize(
    "shape,source",
    [
        (
            "local alias",
            "class S:\n"
            "    def unlocked_via_alias(self):\n"
            "        conn = self._conn\n"
            "        conn.execute('PRAGMA freelist_count')\n",
        ),
        (
            "walrus",
            "class S:\n"
            "    def walrus(self):\n"
            "        return (c := self._conn).execute('SELECT 1')\n",
        ),
        (
            "handed to a helper",
            "class S:\n"
            "    def hand_it_over(self):\n"
            "        return _run(self._conn, 'SELECT 1')\n",
        ),
        (
            "returned out of the lock it was read under",
            "class S:\n"
            "    def leak(self):\n"
            "        with self._write_lock:\n"
            "            return self._conn\n",
        ),
    ],
    ids=lambda v: v if "\n" not in v else "",
)
def test_the_scan_refuses_every_copy_of_the_handle(shape, source):
    """A copy is where the lock stops applying with nothing to show for it.

    Once the handle is bound to a name, driven through an argument, or returned,
    the statement that uses it can be anywhere, including another module. The
    scan cannot follow that, so it refuses the copy instead of ignoring it.
    """
    assert _unguarded_conn_sites(ast.parse(source)), shape


@pytest.mark.parametrize(
    "shape,source,expected",
    [
        (
            "lambda written in the lock, called after it exits",
            "class S:\n"
            "    def with_lambda_escape(self):\n"
            "        with self._write_lock:\n"
            "            f = lambda: self._conn.execute('SELECT 1')\n"
            "        f()\n",
            ["with_lambda_escape at line 4"],
        ),
        (
            "claimed method handed to a thread as a bare reference",
            "class S:\n"
            "    def caller_holds_it(self):\n"
            "        '''Must be called under self._write_lock.'''\n"
            "        self._conn.execute('DROP TABLE x')\n"
            "    def submits_it_to_a_thread(self):\n"
            "        with self._write_lock:\n"
            "            t = Thread(target=self.caller_holds_it)\n"
            "        t.start()\n",
            ["caller_holds_it at line 4"],
        ),
        (
            "claimed method called from a lambda a proved method returns",
            "class S:\n"
            "    def inner(self):\n"
            "        '''Must be called under self._write_lock.'''\n"
            "        self._conn.execute('SELECT 1')\n"
            "    def middle(self):\n"
            "        '''Must be called under self._write_lock.'''\n"
            "        return lambda: self.inner()\n"
            "    def top(self):\n"
            "        with self._write_lock:\n"
            "            g = self.middle()\n"
            "        g()\n",
            ["inner at line 4"],
        ),
    ],
    ids=["lambda", "bare reference", "lambda out of a proved method"],
)
def test_the_scan_refuses_a_callable_written_in_the_lock_but_run_later(
    shape, source, expected
):
    """Writing a callable inside the lock says nothing about when it runs.

    Each of these puts the text lexically under ``with self._write_lock:`` while
    the statement reaches the connection after the lock is released. Judging the
    text where it is written passes all three, which is the whole hole.
    """
    assert _unguarded_conn_sites(ast.parse(source)) == expected, shape


def test_a_lambda_invoked_in_place_inside_the_lock_passes():
    """Conservatism has a floor here too, or the scan gets switched off.

    ``(lambda: ...)()`` runs before the call returns, so the lock is still held.
    """
    source = (
        "class S:\n"
        "    def immediately_invoked(self):\n"
        "        with self._write_lock:\n"
        "            (lambda: self._conn.execute('SELECT 1'))()\n"
    )
    found = _unguarded_conn_sites(ast.parse(source))
    assert found == [], found


def test_a_caller_locked_contract_needs_a_caller_that_locks():
    """The docstring exemption is a claim about callers, so the callers decide it."""
    source = (
        "class S:\n"
        "    def caller_holds_it(self):\n"
        "        '''Must be called under self._write_lock.'''\n"
        "        self._conn.execute('DROP TABLE x')\n"
        "    def careless_caller(self):\n"
        "        self.caller_holds_it()\n"
    )
    found = _unguarded_conn_sites(ast.parse(source))
    assert found == ["caller_holds_it at line 4"], found


def test_a_contract_with_no_caller_in_this_module_stays_unproved():
    source = (
        "class S:\n"
        "    def orphan(self):\n"
        "        '''Must be called under self._write_lock.'''\n"
        "        self._conn.execute('SELECT 1')\n"
    )
    found = _unguarded_conn_sites(ast.parse(source))
    assert found == ["orphan at line 4"], found


def test_contracts_vouching_for_each_other_prove_nothing():
    """Two claims in a ring are still two claims. Neither resolves."""
    source = (
        "class S:\n"
        "    def a(self):\n"
        "        '''Must be called under self._write_lock.'''\n"
        "        self._conn.execute('SELECT 1')\n"
        "        self.b()\n"
        "    def b(self):\n"
        "        '''Must be called under self._write_lock.'''\n"
        "        self._conn.execute('SELECT 2')\n"
        "        self.a()\n"
    )
    found = _unguarded_conn_sites(ast.parse(source))
    assert found == ["a at line 4", "b at line 8"], found


def test_a_chain_of_honest_contracts_still_passes():
    """Conservatism has a floor: a real chain that locks must not be flagged."""
    source = (
        "class S:\n"
        "    def inner(self):\n"
        "        '''Must be called under self._write_lock.'''\n"
        "        self._conn.execute('SELECT 1')\n"
        "    def middle(self):\n"
        "        '''Must be called under self._write_lock.'''\n"
        "        self.inner()\n"
        "    def top(self):\n"
        "        with self._write_lock:\n"
        "            self.middle()\n"
    )
    found = _unguarded_conn_sites(ast.parse(source))
    assert found == [], found
