"""A transient RPC failure must not take the whole process down with it."""

import time

import pytest

from dsc.client import SeafileClient
from dsc.errors import GracefulShutdown


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(time, "sleep", lambda seconds: None)
    return SeafileClient("seafile.example", "user", "pw", "/dsc", token="tok-en")


def test_watch_status_survives_a_transient_rpc_failure(client, monkeypatch):
    """The loop keeps going instead of crashing the container."""
    calls = []

    def flaky_get_status():
        calls.append(1)
        if len(calls) == 1:
            raise ConnectionError("daemon restarting")
        raise GracefulShutdown("SIGTERM")  # ends the otherwise-infinite loop

    monkeypatch.setattr(client, "get_status", flaky_get_status)

    with pytest.raises(GracefulShutdown):
        client.watch_status()

    assert len(calls) == 2, "the loop must retry after the first failure"


def test_watch_status_still_propagates_a_stop_signal(client, monkeypatch):
    """A DscError, such as a stop signal, must still end the loop."""
    monkeypatch.setattr(client, "get_status",
                         lambda: (_ for _ in ()).throw(GracefulShutdown("SIGINT")))

    with pytest.raises(GracefulShutdown):
        client.watch_status()


def test_watch_status_keeps_prior_state_across_a_failed_read(client, monkeypatch, caplog):
    """A failed read is logged and skipped; it must not corrupt prior state."""
    calls = []

    def flaky_get_status():
        calls.append(1)
        if len(calls) == 1:
            return {"Docs": "syncing"}
        if len(calls) == 2:
            raise ConnectionError("daemon restarting")
        raise GracefulShutdown("SIGTERM")

    monkeypatch.setattr(client, "get_status", flaky_get_status)

    with caplog.at_level("WARNING"):
        with pytest.raises(GracefulShutdown):
            client.watch_status()

    assert "Could not read sync status" in caplog.text
    assert len(calls) == 3
