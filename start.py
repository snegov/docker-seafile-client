#!/usr/bin/env python3

import argparse
import logging
import os
import signal
import sys

from dsc import SeafileClient, const
from dsc.config import env_bool, env_int, env_str
from dsc.errors import ConfigError, DscError, GracefulShutdown
from dsc.misc import setup_uid, create_dir, drop_privileges
from dsc.paths import plan_lib_dirs
from dsc.secrets import resolve_secret

_lg = logging.getLogger('dsc')


def handle_signal(signum, frame):
    """Turn a stop signal into an exception so the daemon is stopped on the
    way out instead of the container being killed with the daemon running."""
    raise GracefulShutdown(signal.Signals(signum).name)


def install_signal_handlers():
    for signum in (signal.SIGTERM, signal.SIGINT):
        signal.signal(signum, handle_signal)


def defaults_from_env() -> dict:
    """
    Read every setting from the environment with its documented default.

    Reading these directly leaves an unset variable as None, which reaches
    seaf-cli as the string "None" and silently replaces the documented value.
    """
    return dict(
        server=env_str("SERVER_HOST"),
        username=env_str("USERNAME"),
        password=env_str("PASSWORD"),
        password_file=env_str("PASSWORD_FILE"),
        token=env_str("TOKEN"),
        token_file=env_str("TOKEN_FILE"),
        libraries=env_str("LIBRARY_ID"),
        uid=env_int("SEAFILE_UID", 1000),
        gid=env_int("SEAFILE_GID", 1000),
        upload_limit=env_int("UPLOAD_LIMIT", 0),
        download_limit=env_int("DOWNLOAD_LIMIT", 0),
        delete_confirm_threshold=env_int("DELETE_CONFIRM_THRESHOLD", 500),
        disable_verify_certificate=env_bool("DISABLE_VERIFY_CERTIFICATE", False),
    )


def resolve_libraries(client, requested: str, server: str) -> set:
    """Map the requested names or IDs to library IDs that are not synced yet."""
    libs_to_sync = set()
    for arg_lib in requested.split(sep=":"):
        lib_id = client.get_library_id(arg_lib)
        if lib_id:
            libs_to_sync.add(lib_id)
        else:
            _lg.warning("Library %s is not found on server %s", arg_lib, server)

    # don't start to sync libraries already in sync
    return libs_to_sync - client.get_local_libraries()


def run(client, args, libs_dir: str) -> int:
    """
    Run the client lifecycle and return the process exit code. The daemon is
    always stopped on the way out, including on a failure or a stop signal.
    """
    rc = 0
    try:
        client.init_config()
        client.start_daemon()
        client.configure(args, check_for_daemon=False)

        libs_to_sync = resolve_libraries(client, args.libraries, args.server)

        # Library names come from the server, so the directory for each one is
        # resolved and checked before anything is created or written.
        lib_dirs = plan_lib_dirs(
            {lib_id: client.remote_libraries[lib_id] for lib_id in libs_to_sync},
            libs_dir,
        )
        for lib_id, lib_dir in lib_dirs.items():
            client.sync_lib(lib_id, lib_dir)
        client.watch_status()
    except GracefulShutdown as err:
        _lg.info("Received %s, shutting down", err)
    except DscError as err:
        _lg.error("%s", err)
        rc = 1

    try:
        client.stop_daemon()
    except DscError as err:
        _lg.error("Could not stop seafile daemon cleanly: %s", err)
        rc = 1
    return rc


def main():
    logging.basicConfig(format="%(asctime)s %(message)s", level=logging.INFO)

    parser = argparse.ArgumentParser()
    parser.add_argument("-s", "--server")
    parser.add_argument("-u", "--username")
    parser.add_argument("-p", "--password")
    parser.add_argument("--password-file")
    parser.add_argument("-T", "--token")
    parser.add_argument("--token-file")
    parser.add_argument("-l", "--libraries")
    parser.add_argument("--uid", type=int)
    parser.add_argument("--gid", type=int)
    parser.add_argument("--upload-limit", type=int, default=0)
    parser.add_argument("--download-limit", type=int, default=0)
    parser.add_argument("--disable-verify-certificate", action="store_true")
    parser.add_argument("--delete-confirm-threshold", type=int, default=500)

    try:
        parser.set_defaults(**defaults_from_env())
    except ConfigError as err:
        _lg.error("%s", err)
        return 2
    args = parser.parse_args()
    if not args.server:
        parser.error("Seafile server is not specified")
    if not args.username:
        parser.error("username is not specified")
    if not args.libraries:
        parser.error("library is not specified")

    try:
        password = resolve_secret("PASSWORD", args.password, args.password_file)
        token = resolve_secret("TOKEN", args.token, args.token_file)
    except ConfigError as err:
        _lg.error("%s", err)
        return 2
    if not password and not token:
        parser.error("neither a password nor a token is specified")
    if password and token:
        # seaf-cli behaves the same way: a token makes the password unused.
        _lg.info("Both a password and a token are configured; using the token")

    install_signal_handlers()

    setup_uid(args.uid, args.gid)
    create_dir(const.DEFAULT_APP_DIR)
    drop_privileges(args.uid, args.gid)

    client = SeafileClient(args.server, args.username, password,
                           const.DEFAULT_APP_DIR, token=token)

    # check for deprecated /data directory
    if os.path.isdir(const.DEPRECATED_LIBS_DIR):
        _lg.warning("*** DEPRECATED DIRECTORY FOUND ***")
        _lg.warning("Deprecated directory %s is found, please mount your host directory with"
                    " libraries to %s instead", const.DEPRECATED_LIBS_DIR, const.DEFAULT_LIBS_DIR)
        libs_dir = const.DEPRECATED_LIBS_DIR
    else:
        libs_dir = const.DEFAULT_LIBS_DIR

    return run(client, args, libs_dir)


if __name__ == "__main__":
    sys.exit(main())
