"""Make ``dsc.client`` importable outside the container.

``seafile`` and ``pysearpc`` ship with the Seafile CLI AppImage and only exist
inside the image. The application tests must not need a live server or that
AppImage, so a stub module stands in for the RPC client.
"""

import sys
import types
from unittest import mock

import pytest


def _install_seafile_stub():
    if "seafile" in sys.modules:
        return
    seafile = types.ModuleType("seafile")
    seafile.RpcClient = mock.MagicMock(name="RpcClient")
    sys.modules["seafile"] = seafile


_install_seafile_stub()


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """
    Fail loudly instead of reaching the network.

    The client retries failed requests with backoff, so a test that
    accidentally makes a real request appears to hang rather than fail.
    """
    import requests

    def blocked(self, method, url, *args, **kwargs):
        raise AssertionError(f"Test attempted a real request: {method} {url}")

    monkeypatch.setattr(requests.Session, "request", blocked)
