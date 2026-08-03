"""Read secrets from a variable or a mounted file.

Docker Compose and Swarm secrets arrive as files under /run/secrets, which
keeps them out of the environment. Nothing here ever puts a secret value into
a message: an error about a secret must not leak the secret.
"""

import logging
import os

from dsc.errors import ConfigError

_lg = logging.getLogger(__name__)


def read_secret_file(path: str) -> str:
    """
    Return the secret stored in ``path``.

    Only trailing newlines are removed. Secret files are commonly written with
    one, and a password that silently carries it just fails to authenticate.
    Everything else, including surrounding spaces, is part of the secret.
    """
    if not os.path.isfile(path):
        raise ConfigError(f"Secret file {path} does not exist or is not a file")

    try:
        with open(path, "r") as f:
            secret = f.read()
    except OSError as err:
        raise ConfigError(f"Cannot read secret file {path}: {err.strerror}")

    secret = secret.rstrip("\r\n")
    if not secret:
        raise ConfigError(f"Secret file {path} is empty")
    return secret


def resolve_secret(name: str, value: str, file_path: str) -> str:
    """
    Return the secret named ``name``, from either the variable or the file.

    Supplying both is rejected rather than resolved by precedence: the two
    values are usually meant to be the same, and quietly picking one hides a
    misconfiguration until authentication fails.
    """
    file_name = f"{name}_FILE"
    if value and file_path:
        raise ConfigError(
            f"{name} and {file_name} are both set; use exactly one of them"
        )

    if file_path:
        _lg.info("Reading %s from %s", name, file_path)
        return read_secret_file(file_path)

    return value or None
