"""HTTP requests to the Seafile server must be bounded, not hang forever.

Regression coverage for a measured issue: with no request timeout, the
retry policy waited about 26 minutes against an unreachable host before
giving up. See dsc/const.py for the bounds this enforces.
"""

from unittest import mock

import pytest
import requests

from dsc import const
from dsc.client import SeafileClient
from dsc.errors import NetworkError


@pytest.fixture
def client():
    return SeafileClient("seafile.example", "user", "pw", "/dsc")


def test_client_mounts_a_bounded_retry_policy(client):
    adapter = client.session.get_adapter("https://seafile.example")
    retry = adapter.max_retries
    assert retry.total == const.HTTP_RETRY_TOTAL
    assert retry.backoff_factor == const.HTTP_RETRY_BACKOFF_FACTOR
    assert retry.backoff_max == const.HTTP_RETRY_BACKOFF_MAX


def test_fetching_a_token_passes_a_request_timeout(client):
    with mock.patch.object(client.session, "post") as post:
        post.return_value = mock.Mock(status_code=200, json=lambda: {"token": "tok"})
        assert client.token == "tok"
    _, kwargs = post.call_args
    assert kwargs["timeout"] == const.HTTP_TIMEOUT


def test_fetching_a_token_wraps_a_network_failure(client):
    with mock.patch.object(client.session, "post", side_effect=requests.exceptions.Timeout):
        with pytest.raises(NetworkError):
            _ = client.token


def test_fetching_a_token_reports_url_and_status_on_an_error_response(client):
    with mock.patch.object(client.session, "post") as post:
        post.return_value = mock.Mock(status_code=403, text="Forbidden")
        with pytest.raises(NetworkError, match="auth-token.*403.*Forbidden"):
            _ = client.token


def test_listing_remote_libraries_passes_a_request_timeout(client, monkeypatch):
    monkeypatch.setattr(type(client), "token", "tok")
    with mock.patch.object(client.session, "get") as get:
        get.return_value = mock.Mock(status_code=200, json=lambda: [])
        assert client.remote_libraries == {}
    _, kwargs = get.call_args
    assert kwargs["timeout"] == const.HTTP_TIMEOUT


def test_listing_remote_libraries_wraps_a_network_failure(client, monkeypatch):
    monkeypatch.setattr(type(client), "token", "tok")
    with mock.patch.object(client.session, "get", side_effect=requests.exceptions.ConnectionError):
        with pytest.raises(NetworkError):
            _ = client.remote_libraries


def test_listing_remote_libraries_reports_url_and_status_on_an_error_response(client, monkeypatch):
    monkeypatch.setattr(type(client), "token", "tok")
    with mock.patch.object(client.session, "get") as get:
        get.return_value = mock.Mock(status_code=500, text="Internal Server Error")
        with pytest.raises(NetworkError, match="api2/repos.*500.*Internal Server Error"):
            _ = client.remote_libraries
