#!/usr/bin/env python3

import argparse
import logging
import os
import os.path
import sys

from dsc import SeafileClient, start_seaf_daemon
from dsc.misc import setup_uid, create_dir

_lg = logging.getLogger('dsc')


def main():
    logging.basicConfig(format="%(asctime)s %(message)s", level=logging.INFO)

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
    create_dir(args.data_dir)
    start_seaf_daemon()

    libs_to_sync = set()

    client = SeafileClient(args.host, args.username, args.password)
    for arg_lib in args.libs.split(sep=":"):
        lib_id = client.get_library_id(arg_lib)
        if lib_id:
            libs_to_sync.add(lib_id)
        else:
            _lg.warning("Library %s is not found on server %s", arg_lib, args.host)

    # don't start to sync libraries already in sync
    libs_to_sync -= client.get_local_libraries()

    for lib_id in libs_to_sync:
        client.sync_lib(lib_id, args.data_dir)
    client.watch_status()

    return 0


if __name__ == "__main__":
    sys.exit(main())
