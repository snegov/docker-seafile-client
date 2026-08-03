"""Startup and shutdown must be bounded, checked, and interruptible."""

import argparse
import signal
import subprocess
import time

import pytest

import start
from dsc import client as client_module
from dsc import const
from dsc.client import SeafileClient
from dsc.errors import DaemonError, DaemonTimeout, GracefulShutdown


@pytest.fixture(autouse=True)
def fast_polling(monkeypatch):
    """Keep the bounded waits bounded to milliseconds in tests."""
    monkeypatch.setattr(const, "DAEMON_POLL_PERIOD", 0)
    monkeypatch.setattr(const, "DAEMON_START_TIMEOUT", 0.05)
    monkeypatch.setattr(const, "DAEMON_STOP_TIMEOUT", 0.05)


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(client_module, "create_dir", lambda path: None)
    # A token keeps the tests off the network: without one, authentication
    # would be attempted against the server before syncing.
    return SeafileClient("seafile.example", "user", "pw", "/dsc", token="tok-en")


def fake_runner(returncodes, monkeypatch, stdout=b""):
    """Return exit codes by seaf-cli subcommand; record every call."""
    calls = []

    def fake_run(argv, **kwargs):
        calls.append(argv)
        subcommand = argv[argv.index("seaf-cli") + 1]
        code = returncodes.get(subcommand, 0)
        return subprocess.CompletedProcess(argv, code, stdout=stdout)

    monkeypatch.setattr(subprocess, "run", fake_run)
    return calls


def test_start_daemon_fails_when_the_command_fails(client, monkeypatch):
    fake_runner({"start": 1}, monkeypatch)
    with pytest.raises(DaemonError):
        client.start_daemon()


def test_init_config_fails_when_the_command_fails(client, monkeypatch):
    monkeypatch.setattr(type(client), "config_initialized", property(lambda self: False))
    fake_runner({"init": 2}, monkeypatch)
    with pytest.raises(DaemonError):
        client.init_config()


def test_start_daemon_gives_up_when_the_daemon_never_becomes_ready(client, monkeypatch):
    # "start" succeeds but "status" never does: the daemon never comes up.
    fake_runner({"status": 1}, monkeypatch)

    started = time.monotonic()
    with pytest.raises(DaemonTimeout) as err:
        client.start_daemon()

    assert time.monotonic() - started < 5, "the wait must be bounded"
    assert "ready" in str(err.value).lower()


def test_start_daemon_returns_once_ready(client, monkeypatch):
    fake_runner({}, monkeypatch)  # status returns 0 straight away
    client.start_daemon()


def test_stop_daemon_gives_up_when_the_daemon_never_stops(client, monkeypatch):
    # "status" keeps succeeding, so the daemon never reports itself stopped.
    fake_runner({}, monkeypatch)

    started = time.monotonic()
    with pytest.raises(DaemonTimeout):
        client.stop_daemon()

    assert time.monotonic() - started < 5, "the wait must be bounded"


def test_stop_daemon_succeeds_when_the_daemon_is_already_gone(client, monkeypatch):
    # A stopped daemon makes both "stop" and "status" fail; that is success.
    fake_runner({"stop": 1, "status": 1}, monkeypatch)
    client.stop_daemon()


def test_stop_timeout_fits_inside_the_docker_stop_grace_period():
    """docker stop sends SIGKILL 10s after SIGTERM by default."""
    assert const.DAEMON_STOP_TIMEOUT < 10


def test_configure_fails_when_setting_an_option_fails(client, monkeypatch):
    fake_runner({"config": 1}, monkeypatch)
    with pytest.raises(DaemonError):
        client.configure(argparse.Namespace(upload_limit=100), check_for_daemon=False)


def test_sync_lib_reports_a_failure_without_stopping_other_libraries(client, monkeypatch, caplog):
    fake_runner({"sync": 1}, monkeypatch)
    with caplog.at_level("ERROR"):
        assert client.sync_lib("lib-id", "/dsc/seafile/Docs") is False
    assert "lib-id" in caplog.text


def test_sync_lib_reports_success(client, monkeypatch):
    fake_runner({}, monkeypatch)
    assert client.sync_lib("lib-id", "/dsc/seafile/Docs") is True


class FakeClient:
    """A client whose lifecycle calls are recorded instead of executed."""

    def __init__(self, fail_on=None, error=None):
        self.fail_on = fail_on
        self.error = error or DaemonError("boom")
        self.calls = []
        self.remote_libraries = {"lib-id": "Docs"}

    def __getattr__(self, name):
        def record(*args, **kwargs):
            self.calls.append(name)
            if name == self.fail_on:
                raise self.error
            return True
        return record

    def __record(self, name):
        self.calls.append(name)
        if name == self.fail_on:
            raise self.error

    def get_library_id(self, name):
        self.__record("get_library_id")
        return "lib-id"

    def get_local_libraries(self):
        self.__record("get_local_libraries")
        return set()


ARGS = argparse.Namespace(libraries="Docs", server="seafile.example")


def test_run_stops_the_daemon_after_a_normal_finish():
    client = FakeClient()
    assert start.run(client, ARGS, "/dsc/seafile") == 0
    assert client.calls[-1] == "stop_daemon"


@pytest.mark.parametrize("failing_step", [
    "init_config", "start_daemon", "configure", "get_local_libraries", "watch_status",
])
def test_run_returns_nonzero_and_still_stops_the_daemon_on_failure(failing_step):
    client = FakeClient(fail_on=failing_step)
    assert start.run(client, ARGS, "/dsc/seafile") != 0
    assert client.calls[-1] == "stop_daemon"


def test_run_returns_zero_and_stops_the_daemon_on_shutdown_signal():
    client = FakeClient(fail_on="watch_status", error=GracefulShutdown("SIGTERM"))
    assert start.run(client, ARGS, "/dsc/seafile") == 0
    assert client.calls[-1] == "stop_daemon"


def test_run_reports_failure_even_if_stopping_also_fails():
    client = FakeClient(fail_on="stop_daemon", error=DaemonTimeout("stuck"))
    assert start.run(client, ARGS, "/dsc/seafile") != 0


@pytest.mark.parametrize("signum", [signal.SIGTERM, signal.SIGINT])
def test_signal_handlers_raise_a_graceful_shutdown(signum):
    previous = signal.getsignal(signum)
    try:
        start.install_signal_handlers()
        handler = signal.getsignal(signum)
        with pytest.raises(GracefulShutdown):
            handler(signum, None)
    finally:
        signal.signal(signum, previous)
