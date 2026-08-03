"""Secrets may come from a variable or a mounted file, never ambiguously."""

import pytest

from dsc.errors import ConfigError
from dsc.secrets import read_secret_file, resolve_secret


def write(tmp_path, content, name="secret"):
    path = tmp_path / name
    path.write_text(content)
    return str(path)


@pytest.mark.parametrize("content, expected", [
    ("s3cret", "s3cret"),
    # Secret files are usually written with a trailing newline; a password
    # that silently includes it fails to authenticate with no useful message.
    ("s3cret\n", "s3cret"),
    ("s3cret\r\n", "s3cret"),
    ("s3cret\n\n", "s3cret"),
    # Everything else is part of the secret, including inner and edge spaces.
    ("  s3cret  ", "  s3cret  "),
    ("pa ss", "pa ss"),
    ('pa"ss$(id)`x`', 'pa"ss$(id)`x`'),
    ("паssшörд\n", "паssшörд"),
])
def test_read_secret_file_strips_only_trailing_newlines(tmp_path, content, expected):
    assert read_secret_file(write(tmp_path, content)) == expected


@pytest.mark.parametrize("content", ["", "\n", "\r\n", "\n\n"])
def test_read_secret_file_rejects_an_empty_secret(tmp_path, content):
    with pytest.raises(ConfigError):
        read_secret_file(write(tmp_path, content))


def test_read_secret_file_reports_a_missing_file(tmp_path):
    missing = str(tmp_path / "absent")
    with pytest.raises(ConfigError) as err:
        read_secret_file(missing)
    assert missing in str(err.value)


def test_read_secret_file_never_puts_the_secret_in_the_error(tmp_path):
    path = write(tmp_path, "")
    with pytest.raises(ConfigError) as err:
        read_secret_file(path)
    assert "empty" in str(err.value).lower()


def test_resolve_secret_prefers_nothing_when_neither_is_set():
    assert resolve_secret("PASSWORD", None, None) is None


def test_resolve_secret_reads_the_variable():
    assert resolve_secret("PASSWORD", "s3cret", None) == "s3cret"


def test_resolve_secret_reads_the_file(tmp_path):
    path = write(tmp_path, "s3cret\n")
    assert resolve_secret("PASSWORD", None, path) == "s3cret"


def test_resolve_secret_rejects_two_sources_for_one_secret(tmp_path):
    path = write(tmp_path, "s3cret")
    with pytest.raises(ConfigError) as err:
        resolve_secret("PASSWORD", "other", path)
    assert "PASSWORD" in str(err.value)
    assert "PASSWORD_FILE" in str(err.value)


def test_resolve_secret_conflict_message_hides_both_values(tmp_path):
    path = write(tmp_path, "file-secret")
    with pytest.raises(ConfigError) as err:
        resolve_secret("PASSWORD", "env-secret", path)
    assert "env-secret" not in str(err.value)
    assert "file-secret" not in str(err.value)


def test_resolve_secret_treats_an_empty_variable_as_unset():
    assert resolve_secret("PASSWORD", "", None) is None
