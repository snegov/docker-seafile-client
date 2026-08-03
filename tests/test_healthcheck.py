"""The container HEALTHCHECK must reflect both the daemon and its RPC socket."""

import pytest

from dsc.client import SeafileClient


@pytest.fixture
def client():
    return SeafileClient("seafile.example", "user", "pw", "/dsc", token="tok-en")


def test_healthy_when_daemon_and_rpc_both_respond(client, monkeypatch):
    monkeypatch.setattr(type(client), "daemon_ready", True)
    monkeypatch.setattr(client.rpc, "get_repo_list", lambda a, b: [])
    assert client.is_healthy() is True


def test_unhealthy_when_the_daemon_is_not_ready(client, monkeypatch):
    monkeypatch.setattr(type(client), "daemon_ready", False)
    assert client.is_healthy() is False


def test_unhealthy_when_the_rpc_socket_raises(client, monkeypatch):
    monkeypatch.setattr(type(client), "daemon_ready", True)

    def broken(a, b):
        raise ConnectionError("socket gone")

    monkeypatch.setattr(client.rpc, "get_repo_list", broken)
    assert client.is_healthy() is False


def test_rpc_is_not_checked_when_the_daemon_is_already_down(client, monkeypatch):
    """A dead daemon means a dead socket too; no need to touch it."""
    monkeypatch.setattr(type(client), "daemon_ready", False)
    called = []
    monkeypatch.setattr(client.rpc, "get_repo_list", lambda a, b: called.append(1))
    assert client.is_healthy() is False
    assert not called
