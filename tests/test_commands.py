"""Every subprocess must be an argument list, never a shell string."""

import argparse
import json
import os
import subprocess

import pytest

from dsc import client as client_module
from dsc.errors import ConfigError, DaemonError
from dsc.client import SeafileClient
from dsc.misc import hide_secrets, user_cmd, drop_privileges

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
        token="tok-en",
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


def test_user_cmd_returns_the_command_unchanged():
    # The process itself runs as the seafile user after drop_privileges(),
    # so no per-call re-targeting is needed any more.
    argv = user_cmd(["seaf-cli", "status"])
    assert argv == ["seaf-cli", "status"]


def test_user_cmd_never_invokes_a_shell():
    argv = user_cmd(["seaf-cli", "sync", "-d", "a; rm -rf /"])
    assert "-c" not in argv
    assert not any(arg.endswith("sh") for arg in argv)
    # The dangerous value stays a single, unsplit argument.
    assert argv[-1] == "a; rm -rf /"


def test_user_cmd_rejects_a_string():
    with pytest.raises(TypeError):
        user_cmd("seaf-cli status")


class FakePwInfo:
    pw_dir = "/dsc"


@pytest.fixture
def fake_pwnam(monkeypatch):
    monkeypatch.setattr("pwd.getpwnam", lambda name: FakePwInfo())


def test_drop_privileges_sets_groups_before_gid_before_uid(monkeypatch, fake_pwnam):
    """Order matters: root is needed for each step, and is gone after setuid."""
    calls = []
    monkeypatch.setattr("os.initgroups", lambda user, gid: calls.append(("initgroups", user, gid)))
    monkeypatch.setattr("os.setgid", lambda gid: calls.append(("setgid", gid)))
    monkeypatch.setattr("os.setuid", lambda uid: calls.append(("setuid", uid)))

    drop_privileges(1000, 1000)

    assert [c[0] for c in calls] == ["initgroups", "setgid", "setuid"]


def test_drop_privileges_sets_the_target_environment(monkeypatch, fake_pwnam):
    monkeypatch.setattr("os.initgroups", lambda user, gid: None)
    monkeypatch.setattr("os.setgid", lambda gid: None)
    monkeypatch.setattr("os.setuid", lambda uid: None)

    drop_privileges(1000, 1000)

    assert os.environ["USER"] == "seafile"
    assert os.environ["LOGNAME"] == "seafile"
    assert os.environ["HOME"]


@pytest.mark.parametrize("secret", SHELL_METACHARACTERS)
def test_sync_passes_the_token_as_one_unquoted_argument(client, calls, secret):
    client._SeafileClient__token = secret
    client.sync_lib("lib-id", "/dsc/seafile/Docs")

    argv, _ = calls[-1]
    assert argv[argv.index("-T") + 1] == secret


def test_sync_authenticates_with_the_token_not_the_password(client, calls):
    client.sync_lib("lib-id", "/dsc/seafile/Docs")

    argv, _ = calls[-1]
    assert "-p" not in argv, "the account password must never reach argv"
    assert client.password not in argv


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


@pytest.mark.parametrize("secret", SHELL_METACHARACTERS)
def test_sync_never_logs_the_token_or_the_password(client, calls, caplog, secret):
    client._SeafileClient__token = secret
    client.password = secret + "-pw"
    with caplog.at_level("INFO"):
        client.sync_lib("lib-id", "/dsc/seafile/Docs")

    assert secret not in caplog.text
    assert client.password not in caplog.text


def test_hide_secrets_masks_every_occurrence():
    masked = hide_secrets(["-p", "secret", "-u", "secret-user"], "secret")
    assert masked == ["-p", "********", "-u", "********-user"]


def test_hide_secrets_masks_several_secrets():
    masked = hide_secrets(["-p", "pw", "-T", "tok"], "pw", "tok")
    assert masked == ["-p", "********", "-T", "********"]


def test_hide_secrets_ignores_secrets_that_are_not_set():
    assert hide_secrets(["-T", "tok"], None, "tok") == ["-T", "********"]


def test_hide_secrets_does_not_mutate_the_original():
    argv = ["-p", "secret"]
    hide_secrets(argv, "secret")
    assert argv == ["-p", "secret"]


def test_configure_passes_option_values_as_arguments(client, calls, monkeypatch):
    # Changing an option restarts the daemon, and that restart polls without a
    # timeout. Keep this test on command construction only.
    monkeypatch.setattr(client, "stop_daemon", lambda: None)
    monkeypatch.setattr(client, "start_daemon", lambda: None)

    args = argparse.Namespace(upload_limit=100, unrelated="ignored")
    client.configure(args, check_for_daemon=False)

    argvs = [argv for argv, _ in calls]
    prefix = ["seaf-cli", "config"]
    assert prefix + ["-k", "upload_limit"] in argvs
    assert prefix + ["-k", "upload_limit", "-v", "100"] in argvs
    # An option that seaf-cli does not know about is never forwarded.
    assert not any("ignored" in argv for argv in argvs)


def run_returning(monkeypatch, stdout=b"", returncode=0):
    """Run seaf-cli commands that produce the given output."""
    calls = []

    def fake_run(argv, **kwargs):
        calls.append(argv)
        return subprocess.CompletedProcess(argv, returncode, stdout=stdout)

    monkeypatch.setattr(subprocess, "run", fake_run)
    return calls


def test_local_libraries_are_read_as_json(client, monkeypatch):
    out = json.dumps([
        {"name": "Docs", "id": "id-1", "path": "/dsc/seafile/Docs"},
    ]).encode()
    calls = run_returning(monkeypatch, out)

    assert client.get_local_libraries() == {"id-1"}
    assert "--json" in calls[-1]


@pytest.mark.parametrize("name, path", [
    # Display output is whitespace separated, so these used to be unparseable.
    ("My Docs", "/dsc/seafile/My_Docs"),
    ("Docs", "/mnt/my libraries/Docs"),
    ("My Docs", "/mnt/my libraries/My Docs"),
    ("Ünïcödé ☂", "/dsc/seafile/Ünïcödé_☂"),
    ("tab\tname", "/dsc/seafile/tab_name"),
])
def test_local_libraries_survive_whitespace_in_names_and_paths(client, monkeypatch, name, path):
    out = json.dumps([{"name": name, "id": "id-1", "path": path}]).encode()
    run_returning(monkeypatch, out)

    assert client.get_local_libraries() == {"id-1"}


def test_no_local_libraries_gives_an_empty_set(client, monkeypatch):
    run_returning(monkeypatch, b"[]")
    assert client.get_local_libraries() == set()


def test_local_libraries_reports_unreadable_output(client, monkeypatch):
    run_returning(monkeypatch, b"not json at all")
    with pytest.raises(DaemonError):
        client.get_local_libraries()


def test_local_libraries_reports_a_failed_command(client, monkeypatch):
    run_returning(monkeypatch, b"", returncode=1)
    with pytest.raises(DaemonError):
        client.get_local_libraries()


@pytest.mark.parametrize("payload", [
    b'{"name": "Docs"}',            # an object where a list is expected
    b'[{"name": "Docs"}]',          # an entry with no id
    b'["Docs"]',                    # entries that are not objects
    b'[null]',
    b'null',
    b'42',
])
def test_local_libraries_reports_unexpected_json_shapes(client, monkeypatch, payload):
    """Valid JSON of the wrong shape must not escape as a raw TypeError."""
    run_returning(monkeypatch, payload)
    with pytest.raises(DaemonError):
        client.get_local_libraries()


def test_local_libraries_error_keeps_the_original_cause(client, monkeypatch):
    run_returning(monkeypatch, b"not json at all")
    with pytest.raises(DaemonError) as err:
        client.get_local_libraries()
    assert err.value.__cause__ is not None


def test_configure_never_sends_none_as_a_value(client, calls):
    """A None here reaches seaf-cli as the literal string "None"."""
    with pytest.raises(ConfigError):
        client.configure(argparse.Namespace(upload_limit=None), check_for_daemon=False)

    for argv, _ in calls:
        assert "None" not in argv


@pytest.mark.parametrize("value, expected", [
    (True, "true"),
    (False, "false"),
    (0, "0"),
    (500, "500"),
])
def test_configure_renders_values_the_way_seaf_cli_stores_them(
        client, calls, monkeypatch, value, expected):
    # Changing an option restarts the daemon; keep this on the value only.
    monkeypatch.setattr(client, "stop_daemon", lambda: None)
    monkeypatch.setattr(client, "start_daemon", lambda: None)

    client.configure(argparse.Namespace(disable_verify_certificate=value)
                     if isinstance(value, bool)
                     else argparse.Namespace(upload_limit=value),
                     check_for_daemon=False)

    setting = [argv for argv, _ in calls if "-v" in argv][-1]
    assert setting[setting.index("-v") + 1] == expected
