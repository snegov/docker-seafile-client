#!/usr/bin/env python3

import argparse
import logging
import os
import os.path
import sys

from dsc import SeafileClient, const
from dsc.misc import setup_uid, create_dir

_lg = logging.getLogger('dsc')


def main():
    logging.basicConfig(format="%(asctime)s %(message)s", level=logging.INFO)

    parser = argparse.ArgumentParser()
    parser.add_argument("-s", "--server")
    parser.add_argument("-u", "--username")
    parser.add_argument("-p", "--password")
    parser.add_argument("-l", "--libraries")
    parser.add_argument("--uid", type=int)
    parser.add_argument("--gid", type=int)
    parser.add_argument("--upload-limit", type=int, default=0)
    parser.add_argument("--download-limit", type=int, default=0)
    parser.add_argument("--disable-verify-certificate", action="store_true")
    parser.add_argument("--delete-confirm-threshold", type=int, default=500)

    parser.set_defaults(
        server=os.getenv("SERVER_HOST"),
        username=os.getenv("USERNAME"),
        password=os.getenv("PASSWORD"),
        libraries=os.getenv("LIBRARY_ID"),
        uid=os.getenv("SEAFILE_UID", default=1000),
        gid=os.getenv("SEAFILE_GID", default=1000),
        upload_limit=os.getenv("UPLOAD_LIMIT"),
        download_limit=os.getenv("DOWNLOAD_LIMIT"),
        disable_verify_certificate=os.getenv("DISABLE_VERIFY_CERTIFICATE") in ("true", "1", "True"),
        delete_confirm_threshold=os.getenv("DELETE_CONFIRM_THRESHOLD"),
    )
    args = parser.parse_args()
    if not args.server:
        parser.error("Seafile server is not specified")
    if not args.username:
        parser.error("username is not specified")
    if not args.password:
        parser.error("password is not specified")
    if not args.libraries:
        parser.error("library is not specified")

    setup_uid(args.uid, args.gid)
    create_dir(const.DEFAULT_APP_DIR)

    client = SeafileClient(args.server, args.username, args.password, const.DEFAULT_APP_DIR)
    client.init_config()
    client.start_daemon()
    client.configure(args, check_for_daemon=False)

    libs_to_sync = set()
    for arg_lib in args.libraries.split(sep=":"):
        lib_id = client.get_library_id(arg_lib)
        if lib_id:
            libs_to_sync.add(lib_id)
        else:
            _lg.warning("Library %s is not found on server %s", arg_lib, args.server)

    # don't start to sync libraries already in sync
    libs_to_sync -= client.get_local_libraries()

    # check for deprecated /data directory
    if os.path.isdir(const.DEPRECATED_LIBS_DIR):
        _lg.warning("*** DEPRECATED DIRECTORY FOUND ***")
        _lg.warning("Deprecated directory %s is found, please mount your host directory with"
                    " libraries to %s instead", const.DEPRECATED_LIBS_DIR, const.DEFAULT_LIBS_DIR)
        libs_dir = const.DEPRECATED_LIBS_DIR
    else:
        libs_dir = const.DEFAULT_LIBS_DIR

    for lib_id in libs_to_sync:
        client.sync_lib(lib_id, libs_dir)
    client.watch_status()

    client.stop_daemon()
    return 0


if __name__ == "__main__":
    sys.exit(main())
