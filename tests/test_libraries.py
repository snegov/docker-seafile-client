"""A library set must resolve to exactly one library ID per entry, or fail."""

import pytest

from dsc.client import SeafileClient
from dsc.errors import ConfigError
from start import resolve_libraries


@pytest.fixture
def client(monkeypatch):
    c = SeafileClient("seafile.example", "user", "pw", "/dsc")
    monkeypatch.setattr(type(c), "remote_libraries", {
        "id-1": "Docs",
        "id-2": "Docs",
        "id-3": "Photos",
    })
    monkeypatch.setattr(c, "get_local_libraries", lambda: set())
    return c


def test_get_library_id_resolves_a_unique_name(client):
    assert client.get_library_id("Photos") == "id-3"


def test_get_library_id_resolves_by_id(client):
    assert client.get_library_id("id-1") == "id-1"


def test_get_library_id_returns_none_for_no_match(client):
    assert client.get_library_id("Missing") is None


def test_get_library_id_rejects_an_ambiguous_name(client):
    with pytest.raises(ConfigError, match="Docs.*2 libraries"):
        client.get_library_id("Docs")


def test_resolve_libraries_rejects_an_empty_requested_set(client):
    with pytest.raises(ConfigError, match="empty entry"):
        resolve_libraries(client, "", "seafile.example")


@pytest.mark.parametrize("requested", ["Photos:", ":Photos", "Photos::id-1"])
def test_resolve_libraries_rejects_an_empty_entry_between_separators(client, requested):
    with pytest.raises(ConfigError, match="empty entry"):
        resolve_libraries(client, requested, "seafile.example")


def test_resolve_libraries_rejects_an_ambiguous_name_end_to_end(client):
    with pytest.raises(ConfigError, match="Docs"):
        resolve_libraries(client, "Docs", "seafile.example")


def test_resolve_libraries_resolves_unambiguous_names(client):
    assert resolve_libraries(client, "Photos:id-1", "seafile.example") == {"id-3", "id-1"}
