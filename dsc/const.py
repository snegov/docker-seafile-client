DEFAULT_APP_DIR = "/dsc"
DEFAULT_LIBS_DIR = "/dsc/seafile"
DEPRECATED_LIBS_DIR = "/data"
DEFAULT_USERNAME = "seafile"
STATUS_POLL_PERIOD = 1

# Bounds for daemon startup and shutdown, in seconds. The stop timeout has to
# fit inside the grace period of "docker stop", which sends SIGKILL 10 seconds
# after SIGTERM by default, otherwise shutdown is never graceful.
DAEMON_POLL_PERIOD = 1
DAEMON_START_TIMEOUT = 120
DAEMON_STOP_TIMEOUT = 8

AVAILABLE_SEAFCLI_OPTIONS = {
    "delete_confirm_threshold",
    "disable_verify_certificate",
    "upload_limit",
    "download_limit",
}
