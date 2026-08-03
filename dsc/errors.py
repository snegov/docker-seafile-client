"""Errors that must end the container with a useful message."""


class DscError(Exception):
    """Base class for failures that stop the client."""


class ConfigError(DscError):
    """The container was configured in a way that cannot be acted on."""


class DaemonError(DscError):
    """A seaf-cli command failed."""


class DaemonTimeout(DscError):
    """The daemon did not reach the expected state in time."""


class GracefulShutdown(DscError):
    """SIGTERM or SIGINT was received; stop the daemon and exit cleanly."""
