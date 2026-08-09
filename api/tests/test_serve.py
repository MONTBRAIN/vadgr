"""The launcher's address arithmetic -- what the daemon actually listens on."""

import socket
import sys

import pytest

from api.serve import _listen_socket, main, resolve_hosts


def test_the_transport_address_and_loopback_are_both_kept():
    assert resolve_hosts(["100.67.110.10", "127.0.0.1"]) == ["100.67.110.10", "127.0.0.1"]


def test_a_repeated_address_binds_one_socket_not_two():
    assert resolve_hosts(["127.0.0.1", "127.0.0.1"]) == ["127.0.0.1"]


def test_order_is_preserved_so_the_advertised_address_is_first():
    assert resolve_hosts(["100.1.2.3", "127.0.0.1"])[0] == "100.1.2.3"


def test_binding_every_interface_is_refused_loudly(capsys):
    """Not clamped to something safer: someone asked for every interface, and
    quietly substituting another address would hide the request."""
    assert main(["--host", "0.0.0.0", "--port", "8123"]) == 2
    assert "0.0.0.0" in capsys.readouterr().err


def test_a_listening_socket_is_bound_to_the_address_it_was_given():
    sock = _listen_socket("127.0.0.1", 0)
    try:
        assert sock.getsockname()[0] == "127.0.0.1"
    finally:
        sock.close()


@pytest.mark.skipif(sys.platform == "win32",
                    reason="127.0.0.2 is not bindable on native Windows")
def test_two_addresses_on_one_port_yield_two_listening_sockets():
    """The whole reason the launcher exists: `uvicorn --host` takes one address,
    and the daemon needs the one a phone dials *and* the one gate 0 recognises."""
    port = _free_port()
    socks = [_listen_socket(h, port) for h in ("127.0.0.1", "127.0.0.2")]
    try:
        assert sorted(s.getsockname()[0] for s in socks) == ["127.0.0.1", "127.0.0.2"]
    finally:
        for s in socks:
            s.close()


def test_the_same_address_twice_is_a_real_conflict():
    """Which is why resolve_hosts de-duplicates before anything is opened."""
    port = _free_port()
    first = _listen_socket("127.0.0.1", port)
    try:
        with pytest.raises(OSError):
            _listen_socket("127.0.0.1", port).close()
    finally:
        first.close()


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_windows_does_not_get_so_reuseaddr():
    """The flag's meaning is not the same on both: on POSIX it rebinds through
    TIME_WAIT, on Windows it lets another process take the address away. A
    daemon running with the owner's credentials must not be hijackable, so the
    branch is per-OS rather than written once and assumed portable."""
    import api.serve as serve

    seen = []

    class _Sock:
        def setsockopt(self, *args): seen.append(args)
        def bind(self, addr): pass
        def listen(self, backlog): pass
        def set_inheritable(self, flag): pass

    original, socket_cls = serve._IS_WINDOWS, socket.socket
    try:
        socket.socket = lambda *a, **kw: _Sock()
        serve._IS_WINDOWS = True
        serve._listen_socket("127.0.0.1", 8123)
        assert seen == []
        serve._IS_WINDOWS = False
        serve._listen_socket("127.0.0.1", 8123)
        assert (socket.SOL_SOCKET, socket.SO_REUSEADDR, 1) in seen
    finally:
        socket.socket = socket_cls
        serve._IS_WINDOWS = original


class TestTheDaemonsOwnLogsAreReachable:
    """uvicorn configures its own loggers and nothing else, so an app logger
    propagates to a root logger with no handler and is dropped at WARNING.

    Asserted by actually applying the config and emitting, not by reading the
    dict: a config that names a logger but wires it to no handler would satisfy
    a structural check and still swallow the record.
    """

    def test_an_app_log_record_reaches_a_handler(self, capsys):
        import logging
        import logging.config

        from api.serve import log_config

        saved = {
            name: (logging.getLogger(name).handlers[:], logging.getLogger(name).level,
                   logging.getLogger(name).propagate)
            for name in ("api", "engine", "cli", "uvicorn", "uvicorn.error", "uvicorn.access")
        }
        try:
            logging.config.dictConfig(log_config())
            logging.getLogger("api.persistence.database").info("migrating the database")
            captured = capsys.readouterr()
        finally:
            for name, (handlers, level, propagate) in saved.items():
                logger = logging.getLogger(name)
                logger.handlers[:] = handlers
                logger.setLevel(level)
                logger.propagate = propagate

        assert "migrating the database" in captured.err + captured.out

    def test_every_app_package_is_named(self):
        from api.serve import _APP_LOGGERS, log_config

        loggers = log_config()["loggers"]
        for name in _APP_LOGGERS:
            assert loggers[name]["handlers"], f"{name} is named but wired to no handler"
        # uvicorn's own configuration must survive the extension.
        assert "uvicorn" in loggers
