"""Tests for the remote (WebSocket) KataGo engine's reconnect logic.

These use an in-process fake WebSocket so no network/server is needed:
`create_connection` is monkeypatched to hand out controllable sockets
whose recv()/send()/close() we drive from the test thread.
"""

import queue
import threading
import time

import pytest
from websocket import WebSocketException

from katrain.core import remote_engine
from katrain.core.remote_engine import RemoteKataGoEngine


class FakeWS:
    """Minimal stand-in for a websocket-client connection."""

    def __init__(self):
        self.sent = []
        self._recv = queue.Queue()
        self.closed = False

    def recv_data(self, control_frame=True):
        item = self._recv.get()  # blocks like a real recv
        if isinstance(item, BaseException):
            raise item
        return item

    def send(self, payload):
        if self.closed:
            raise WebSocketException("send on closed socket")
        self.sent.append(payload)

    def close(self):
        self.closed = True
        self._recv.put(WebSocketException("closed"))

    def drop(self):
        """Simulate the server/network dropping the connection."""
        self._recv.put(WebSocketException("connection lost"))


class FakeControls:
    def set_status(self, *args, **kwargs):
        pass


class FakeKatrain:
    """Records calls (e.g. the engine_recovery_popup trigger)."""

    def __init__(self):
        self.controls = FakeControls()
        self.calls = []
        self.update_state = lambda *a, **k: None

    def log(self, *args, **kwargs):
        pass

    def __call__(self, *args, **kwargs):
        self.calls.append(args)


def wait_until(pred, timeout=5.0, interval=0.02):
    end = time.time() + timeout
    while time.time() < end and not pred():
        time.sleep(interval)
    return pred()


def popup_codes(katrain):
    return [args[2] for args in katrain.calls if args and args[0] == "engine_recovery_popup"]


@pytest.fixture
def fast_backoff(monkeypatch):
    monkeypatch.setattr(RemoteKataGoEngine, "RECONNECT_BACKOFF_S", 0.01)
    monkeypatch.setattr(RemoteKataGoEngine, "RECONNECT_MAX_BACKOFF_S", 0.02)


def test_reconnect_resends_outstanding_queries(monkeypatch, fast_backoff):
    created = []

    def factory(*args, **kwargs):
        ws = FakeWS()
        created.append(ws)
        return ws

    monkeypatch.setattr(remote_engine, "create_connection", factory)

    katrain = FakeKatrain()
    engine = RemoteKataGoEngine(katrain, {"remote_url": "ws://test", "allow_recovery": True})
    try:
        assert wait_until(lambda: len(created) == 1)
        ws1 = created[0]

        engine.send_query({"foo": "bar"}, lambda *a: None, None)
        assert wait_until(lambda: len(ws1.sent) == 1)
        assert wait_until(lambda: len(engine.queries) == 1)

        # Connection drops while a query is outstanding.
        ws1.drop()

        # A new connection is established transparently...
        assert wait_until(lambda: len(created) == 2)
        ws2 = created[1]
        assert wait_until(lambda: engine.ws is ws2)

        # ...and the in-flight query is re-sent on it.
        assert wait_until(lambda: len(ws2.sent) >= 1)

        # No local-engine recovery popup was shown.
        assert popup_codes(katrain) == []
    finally:
        engine.shutdown()


def test_reconnect_failure_opens_recovery_popup(monkeypatch, fast_backoff):
    monkeypatch.setattr(RemoteKataGoEngine, "RECONNECT_ATTEMPTS", 2)
    first = FakeWS()
    n = {"count": 0}

    def factory(*args, **kwargs):
        n["count"] += 1
        if n["count"] == 1:
            return first
        raise WebSocketException("connection refused")

    monkeypatch.setattr(remote_engine, "create_connection", factory)

    katrain = FakeKatrain()
    engine = RemoteKataGoEngine(katrain, {"remote_url": "ws://test", "allow_recovery": True})
    try:
        assert wait_until(lambda: engine.ws is first)

        first.drop()

        # All reconnect attempts fail -> fall back to the recovery popup,
        # tagged as a remote disconnect rather than a local crash.
        assert wait_until(lambda: popup_codes(katrain) == ["REMOTE-DISCONNECTED"])

        # The popup is told this is a remote engine so it shows remote-
        # specific advice (check URL) instead of the local executable hints.
        popup_call = next(args for args in katrain.calls if args and args[0] == "engine_recovery_popup")
        assert popup_call[3] == "remote"
    finally:
        engine.shutdown()


def test_check_alive_polling_during_reconnect_does_not_suppress_popup(monkeypatch, fast_backoff):
    # Reproduces the ai.py move loops, which spin on check_alive(exception_if_dead=True)
    # every ~10ms. While reconnecting the socket is briefly None; those polls must not
    # latch the engine "dead" and steal the recovery popup that fires on real failure.
    monkeypatch.setattr(RemoteKataGoEngine, "RECONNECT_ATTEMPTS", 4)
    first = FakeWS()
    n = {"count": 0}

    def factory(*args, **kwargs):
        n["count"] += 1
        if n["count"] == 1:
            return first
        raise WebSocketException("connection refused")

    monkeypatch.setattr(remote_engine, "create_connection", factory)

    katrain = FakeKatrain()
    engine = RemoteKataGoEngine(katrain, {"remote_url": "ws://test", "allow_recovery": True})

    stop = threading.Event()
    seen_alive_while_reconnecting = {"v": False}

    def poller():
        while not stop.is_set():
            alive = engine.check_alive(exception_if_dead=True)
            if engine._reconnecting and alive:
                seen_alive_while_reconnecting["v"] = True
            time.sleep(0.001)

    t = threading.Thread(target=poller, daemon=True)
    try:
        assert wait_until(lambda: engine.ws is first)
        t.start()
        first.drop()

        # Despite aggressive polling, the popup still fires exactly once.
        assert wait_until(lambda: popup_codes(katrain) == ["REMOTE-DISCONNECTED"])
        time.sleep(0.05)  # let the poller keep hammering after the report
        assert popup_codes(katrain) == ["REMOTE-DISCONNECTED"]
        # And check_alive reported "alive" during the reconnect window, not dead.
        assert seen_alive_while_reconnecting["v"]
    finally:
        stop.set()
        t.join(timeout=1)
        engine.shutdown()


def test_new_game_clears_resend_backlog(monkeypatch, fast_backoff):
    created = []

    def factory(*args, **kwargs):
        ws = FakeWS()
        created.append(ws)
        return ws

    monkeypatch.setattr(remote_engine, "create_connection", factory)

    katrain = FakeKatrain()
    engine = RemoteKataGoEngine(katrain, {"remote_url": "ws://test", "allow_recovery": True})
    try:
        ws1 = created[0]
        engine.send_query({"foo": "bar"}, lambda *a: None, None)
        assert wait_until(lambda: len(engine.sent_payloads) == 1)

        # Starting a new game drops outstanding queries; they must not be
        # resurrected by a later reconnect.
        engine.on_new_game()
        assert engine.sent_payloads == {}

        ws1.drop()
        assert wait_until(lambda: len(created) == 2)
        ws2 = created[1]
        assert wait_until(lambda: engine.ws is ws2)
        # The previous game's analysis query is not resurrected (a leftover
        # `terminate` command queued by on_new_game may still be sent).
        time.sleep(0.1)
        assert all("foo" not in payload for payload in ws2.sent)
    finally:
        engine.shutdown()
