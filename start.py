#!/usr/bin/env python3

import argparse
import os
import os.path
import sys

from seafile_client import SeafileClient, start_seaf_daemon
from seafile_client.misc import setup_uid, create_dir


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--uid", default=os.getenv("SEAFILE_UID", default=1000), type=int)
    parser.add_argument("--gid", default=os.getenv("SEAFILE_GID", default=100), type=int)
    parser.add_argument("--data-dir", default=os.getenv("DATA_DIR", default="/data"))
    parser.add_argument("--host", default=os.getenv("SERVER_HOST"))
    parser.add_argument("--username", default=os.getenv("USERNAME"))
    parser.add_argument("--password", default=os.getenv("PASSWORD"))
    parser.add_argument("--libs", default=os.getenv("LIBRARY_ID"))
    args = parser.parse_args()

    setup_uid(args.uid, args.gid)
    start_seaf_daemon()
    create_dir(args.data_dir)
    client = SeafileClient(args.host, args.username, args.password)
    for lib_id in args.libs.split(sep=":"):
        client.sync_lib(lib_id, args.data_dir)
    client.watch_status()

    return 0


if __name__ == "__main__":
    sys.exit(main())
