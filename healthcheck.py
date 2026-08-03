#!/usr/bin/env python3
"""Docker HEALTHCHECK entry point.

Exits 0 if the seafile daemon and its RPC socket both respond, 1 otherwise.
Runs as a separate, short-lived process on every check, so it needs no
credentials and touches no state the main process owns.
"""

import sys

from dsc import const
from dsc.client import SeafileClient


def main() -> int:
    client = SeafileClient(host="unused", user="unused", app_dir=const.DEFAULT_APP_DIR)
    return 0 if client.is_healthy() else 1


if __name__ == "__main__":
    sys.exit(main())
