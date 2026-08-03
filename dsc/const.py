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

# Bounds for HTTP requests to the Seafile server. Without a request timeout,
# a total=30/backoff_factor=2/backoff_max=60 retry policy was measured to
# take about 26 minutes against an unreachable host before giving up, which
# is indistinguishable from a hang. HTTP_TIMEOUT is (connect, read); the
# retry budget below now bounds the worst case to a few minutes instead.
HTTP_TIMEOUT = (10, 30)
HTTP_RETRY_TOTAL = 5
HTTP_RETRY_BACKOFF_FACTOR = 1
HTTP_RETRY_BACKOFF_MAX = 30

AVAILABLE_SEAFCLI_OPTIONS = {
    "delete_confirm_threshold",
    "disable_verify_certificate",
    "upload_limit",
    "download_limit",
}
