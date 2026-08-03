"""Typed reading of the container's environment.

Everything in the environment is text, including values the client later
compares as numbers or passes to seaf-cli. Reading them directly leaves two
failures that are silent until much later: an unset variable becomes None and
reaches seaf-cli as the string "None", and a numeric setting stays a string
that never equals the integer it is compared against.
"""

import os

from dsc.errors import ConfigError

_TRUE_VALUES = {"true", "1", "yes", "on"}
_FALSE_VALUES = {"false", "0", "no", "off"}


def env_str(name: str, default: str = None) -> str:
    """Return a text setting. An empty variable counts as unset."""
    value = os.getenv(name)
    if value is None or value == "":
        return default
    return value


def env_int(name: str, default: int, minimum: int = 0) -> int:
    """
    Return a numeric setting as an int, never as text and never as None.

    Values below ``minimum`` are rejected: a negative speed limit or deletion
    threshold is not something to pass on to seaf-cli and hope for the best.
    """
    raw = env_str(name)
    if raw is None:
        return default

    stripped = raw.strip()
    try:
        value = int(stripped, 10)
    except ValueError:
        raise ConfigError(
            f"{name} must be a whole number, got {stripped!r}"
        )

    if value < minimum:
        raise ConfigError(
            f"{name} must be {minimum} or greater, got {stripped!r}"
        )
    return value


def env_bool(name: str, default: bool = False) -> bool:
    """Return a boolean setting, accepting the usual spellings."""
    raw = env_str(name)
    if raw is None:
        return default

    value = raw.strip().lower()
    if value in _TRUE_VALUES:
        return True
    if value in _FALSE_VALUES:
        return False

    accepted = ", ".join(sorted(_TRUE_VALUES | _FALSE_VALUES))
    raise ConfigError(f"{name} must be one of {accepted}, got {raw.strip()!r}")
