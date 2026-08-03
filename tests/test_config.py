"""The environment is untyped text; everything derived from it is checked."""

import pytest

import start
from dsc.config import env_bool, env_int, env_str
from dsc.errors import ConfigError


@pytest.fixture
def env(monkeypatch):
    def set_env(**values):
        for name, value in values.items():
            if value is None:
                monkeypatch.delenv(name, raising=False)
            else:
                monkeypatch.setenv(name, value)
    return set_env


@pytest.mark.parametrize("raw, expected", [
    (None, 7),        # unset keeps the documented default
    ("", 7),          # an empty variable is the same as unset
    ("0", 0),         # zero is a real value, not "missing"
    ("1", 1),
    ("4096", 4096),
    (" 42 ", 42),
    # int() accepts any Unicode decimal digit and normalises it; the value
    # leaves as an ASCII integer, so this is harmless rather than rejected.
    ("\u0663", 3),
])
def test_env_int_accepts(env, raw, expected):
    env(LIMIT=raw)
    assert env_int("LIMIT", 7) == expected


@pytest.mark.parametrize("raw", ["-1", "-0.5", "abc", "1.5", "1e3", "0x10", "1 2", "٣ x"])
def test_env_int_rejects(env, raw):
    env(LIMIT=raw)
    with pytest.raises(ConfigError) as err:
        env_int("LIMIT", 7)
    assert "LIMIT" in str(err.value)
    assert raw.strip() in str(err.value)


def test_env_int_allows_a_negative_value_when_permitted(env):
    env(LIMIT="-1")
    assert env_int("LIMIT", 7, minimum=-1) == -1


@pytest.mark.parametrize("raw, expected", [
    (None, False),
    ("", False),
    ("true", True), ("True", True), ("TRUE", True),
    ("1", True), ("yes", True), ("on", True),
    ("false", False), ("False", False), ("0", False),
    ("no", False), ("off", False), (" true ", True),
])
def test_env_bool_accepts(env, raw, expected):
    env(FLAG=raw)
    assert env_bool("FLAG", False) is expected


@pytest.mark.parametrize("raw", ["maybe", "2", "-1", "y3s", "truthy"])
def test_env_bool_rejects(env, raw):
    env(FLAG=raw)
    with pytest.raises(ConfigError) as err:
        env_bool("FLAG", False)
    assert "FLAG" in str(err.value)


def test_env_bool_keeps_a_true_default_when_unset(env):
    env(FLAG=None)
    assert env_bool("FLAG", True) is True


@pytest.mark.parametrize("raw, expected", [
    (None, None), ("", None), ("value", "value"), ("  spaced  ", "  spaced  "),
])
def test_env_str(env, raw, expected):
    env(NAME=raw)
    assert env_str("NAME") == expected


def test_a_default_container_gets_exactly_the_documented_defaults(monkeypatch):
    """The values the README promises when nothing optional is configured."""
    for name in ("UPLOAD_LIMIT", "DOWNLOAD_LIMIT", "DELETE_CONFIRM_THRESHOLD",
                 "SEAFILE_UID", "SEAFILE_GID", "DISABLE_VERIFY_CERTIFICATE"):
        monkeypatch.delenv(name, raising=False)

    defaults = start.defaults_from_env()

    assert defaults["upload_limit"] == 0
    assert defaults["download_limit"] == 0
    assert defaults["delete_confirm_threshold"] == 500
    assert defaults["uid"] == 1000
    assert defaults["gid"] == 1000
    assert defaults["disable_verify_certificate"] is False


def test_no_default_is_none_where_a_value_is_documented(monkeypatch):
    """A None here reaches seaf-cli as the literal string "None"."""
    for name in ("UPLOAD_LIMIT", "DOWNLOAD_LIMIT", "DELETE_CONFIRM_THRESHOLD",
                 "SEAFILE_UID", "SEAFILE_GID"):
        monkeypatch.delenv(name, raising=False)

    defaults = start.defaults_from_env()
    for key in ("upload_limit", "download_limit", "delete_confirm_threshold",
                "uid", "gid"):
        assert defaults[key] is not None, f"{key} must never default to None"


def test_numeric_settings_are_integers_not_strings(monkeypatch):
    """A string UID never equals the integer it is compared against."""
    monkeypatch.setenv("SEAFILE_UID", "1000")
    monkeypatch.setenv("UPLOAD_LIMIT", "50")

    defaults = start.defaults_from_env()
    assert defaults["uid"] == 1000 and isinstance(defaults["uid"], int)
    assert defaults["upload_limit"] == 50 and isinstance(defaults["upload_limit"], int)
