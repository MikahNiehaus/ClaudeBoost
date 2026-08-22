"""
server_ctl._port_in_use must answer "is a server listening", not "would a bind
succeed right now".

Those differ for up to a minute after every stop. A bind without SO_REUSEADDR
fails while the port holds a socket in TIME_WAIT, which is the state a server
leaves behind when it exits. `start` then refuses with "already running" while
nothing is listening, and the only remedy is to wait, which the message does not
say. Observed for real: `start` refused immediately after `stop`.

A connect probe gets both cases right. A live listener accepts, so a genuinely
running server is still detected, which is the failure the bind probe was
originally written for. A TIME_WAIT socket refuses, so it correctly reads as
free, and the server can rebind because aiohttp's run_app uses reuse_address.

Run: python -m pytest tests/test_server_ctl_port_check.py -v
"""

import importlib.util
import socket
import threading
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def sc():
    spec = importlib.util.spec_from_file_location(
        "server_ctl", REPO / "clean-rag" / "cli" / "server_ctl.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def test_a_listening_server_is_detected(sc):
    """The case the original bind probe existed for must keep working."""
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", 0))
    port = srv.getsockname()[1]
    srv.listen(1)
    try:
        assert sc._port_in_use(port) is True
    finally:
        srv.close()


def test_an_empty_port_is_free(sc):
    assert sc._port_in_use(_free_port()) is False


def test_a_port_left_in_time_wait_reads_as_free(sc):
    """
    The regression this fixes.

    Stand up a listener, take one connection, close the server side first so the
    server socket enters TIME_WAIT, then ask. A bind probe says in use here. The
    honest answer is free, because nothing is listening.
    """
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.bind(("127.0.0.1", 0))
    port = srv.getsockname()[1]
    srv.listen(1)

    release = threading.Event()

    def client():
        c = socket.create_connection(("127.0.0.1", port))
        release.wait(2)
        c.close()

    t = threading.Thread(target=client, daemon=True)
    t.start()
    conn, _ = srv.accept()

    # Server side closes first, which is what puts it into TIME_WAIT.
    conn.close()
    srv.close()
    release.set()
    t.join(timeout=2)

    # Confirm the port really is in the state this test is about, so a passing
    # assertion below cannot be an accident of the socket having been reaped.
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        try:
            probe.bind(("127.0.0.1", port))
            pytest.skip("port was released before TIME_WAIT could be observed")
        except OSError:
            pass

    assert sc._port_in_use(port) is False, (
        "a port held only by TIME_WAIT must read as free, otherwise start "
        "refuses with 'already running' for up to a minute after every stop"
    )


def test_the_check_does_not_leave_a_socket_behind(sc):
    """It must not itself bind the port it is asked about."""
    port = _free_port()
    for _ in range(3):
        assert sc._port_in_use(port) is False

    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        srv.bind(("127.0.0.1", port))
    except OSError as exc:
        pytest.fail(f"_port_in_use left the port occupied: {exc}")
    finally:
        srv.close()
