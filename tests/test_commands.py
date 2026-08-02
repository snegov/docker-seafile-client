"""Every subprocess must be an argument list, never a shell string."""

import argparse
import subprocess

import pytest

from dsc import client as client_module
from dsc import const
from dsc.client import SeafileClient
from dsc.misc import hide_password, user_cmd

# Values that would be interpreted by a shell if a command were ever joined
# into a string and handed to ``su -c``.
SHELL_METACHARACTERS = [
    'pa"ss',
    "pa'ss",
    "pa$(id)ss",
    "pa`id`ss",
    "pass; rm -rf /",
    "pass && curl evil.example",
    "pass | tee /tmp/x",
    "pass\nrm -rf /",
    "pass with spaces",
    "pass\\backslash",
    "паssшörд",
]


@pytest.fixture
def client():
    return SeafileClient(
        host="seafile.example",
        user="user@example",
        passwd="s3cret",
        app_dir="/dsc",
    )


@pytest.fixture
def calls(monkeypatch):
    """Capture every subprocess invocation instead of running it."""
    recorded = []

    def fake_run(argv, **kwargs):
        recorded.append((argv, kwargs))
        return subprocess.CompletedProcess(argv, 0, stdout=b"")

    monkeypatch.setattr(subprocess, "run", fake_run)
    # Directory creation is covered by the path tests; keep the real
    # filesystem out of command construction.
    monkeypatch.setattr(client_module, "create_dir", lambda path: None)
    return recorded


def test_user_cmd_uses_runuser_without_a_shell():
    argv = user_cmd(["seaf-cli", "status"])
    assert argv == ["runuser", "-u", const.DEFAULT_USERNAME, "--", "seaf-cli", "status"]


def test_user_cmd_never_invokes_a_shell():
    argv = user_cmd(["seaf-cli", "sync", "-d", "a; rm -rf /"])
    assert "-c" not in argv
    assert not any(arg.endswith("sh") for arg in argv)
    # The dangerous value stays a single, unsplit argument.
    assert argv[-1] == "a; rm -rf /"


def test_user_cmd_rejects_a_string():
    with pytest.raises(TypeError):
        user_cmd("seaf-cli status")


@pytest.mark.parametrize("password", SHELL_METACHARACTERS)
def test_sync_passes_password_as_one_unquoted_argument(client, calls, password):
    client.password = password
    client.sync_lib("lib-id", "/dsc/seafile/Docs")

    argv, _ = calls[-1]
    assert argv[argv.index("-p") + 1] == password


@pytest.mark.parametrize("lib_dir", [
    "/dsc/seafile/a\"; touch /tmp/pwned; #",
    "/dsc/seafile/$(id)",
    "/dsc/seafile/`id`",
    "/dsc/seafile/name with spaces",
])
def test_sync_passes_library_dir_as_one_argument(client, calls, lib_dir):
    client.sync_lib("lib-id", lib_dir)

    argv, _ = calls[-1]
    assert argv[argv.index("-d") + 1] == lib_dir


def test_sync_command_is_a_list_of_strings(client, calls):
    client.sync_lib("lib-id", "/dsc/seafile/Docs")

    argv, kwargs = calls[-1]
    assert isinstance(argv, list)
    assert all(isinstance(arg, str) for arg in argv)
    assert kwargs.get("shell") is not True


@pytest.mark.parametrize("password", SHELL_METACHARACTERS)
def test_sync_never_logs_the_password(client, calls, caplog, password):
    client.password = password
    with caplog.at_level("INFO"):
        client.sync_lib("lib-id", "/dsc/seafile/Docs")

    assert password not in caplog.text


def test_hide_password_masks_every_occurrence():
    masked = hide_password(["-p", "secret", "-u", "secret-user"], "secret")
    assert masked == ["-p", "********", "-u", "********-user"]


def test_hide_password_does_not_mutate_the_original():
    argv = ["-p", "secret"]
    hide_password(argv, "secret")
    assert argv == ["-p", "secret"]


def test_configure_passes_option_values_as_arguments(client, calls, monkeypatch):
    # Changing an option restarts the daemon, and that restart polls without a
    # timeout. Keep this test on command construction only.
    monkeypatch.setattr(client, "stop_daemon", lambda: None)
    monkeypatch.setattr(client, "start_daemon", lambda: None)

    args = argparse.Namespace(upload_limit=100, unrelated="ignored")
    client.configure(args, check_for_daemon=False)

    argvs = [argv for argv, _ in calls]
    prefix = ["runuser", "-u", const.DEFAULT_USERNAME, "--", "seaf-cli", "config"]
    assert prefix + ["-k", "upload_limit"] in argvs
    assert prefix + ["-k", "upload_limit", "-v", "100"] in argvs
    # An option that seaf-cli does not know about is never forwarded.
    assert not any("ignored" in argv for argv in argvs)
