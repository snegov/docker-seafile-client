import argparse
import json
import logging
import os
import subprocess
import time
from typing import Optional

from cached_property import cached_property_with_ttl
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import seafile

from dsc import const
from dsc.errors import ConfigError, DaemonError, DaemonTimeout, NetworkError
from dsc.misc import config_value, create_dir, hide_secrets, user_cmd

_lg = logging.getLogger(__name__)


class SeafileClient:
    def __init__(self,
                 host: str,
                 user: str,
                 passwd: str = None,
                 app_dir: str = const.DEFAULT_APP_DIR,
                 token: str = None):
        self.user = user
        self.password = passwd
        self.app_dir = os.path.abspath(app_dir)
        self.rpc = seafile.RpcClient(os.path.join(self.app_dir, 'seafile-data', 'seafile.sock'))
        # A token supplied by the operator is used as is; otherwise one is
        # fetched from the server with the password.
        self.__token = token

        # determine server URL (assume HTTPS unless explicitly specified)
        if host.startswith('http://') or host.startswith('https://'):
            self.url = host.rstrip('/')
        else:
            self.url = f"https://{host}"

        # configure session with retry strategy
        # enable urllib3 retry logging at DEBUG level (shows retry attempts)
        urllib3_logger = logging.getLogger("urllib3.connectionpool")
        urllib3_logger.setLevel(logging.DEBUG)
        urllib3_logger.propagate = True

        self.session = requests.Session()
        retry_strategy = Retry(
            total=const.HTTP_RETRY_TOTAL,
            backoff_factor=const.HTTP_RETRY_BACKOFF_FACTOR,
            backoff_max=const.HTTP_RETRY_BACKOFF_MAX,
            status_forcelist=[500, 502, 503, 504],
            allowed_methods=["GET", "POST"]
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

    def __str__(self):
        return f"SeafileClient({self.user}@{self.url})"

    def __gen_cmd(self, argv: list) -> list:
        return user_cmd(argv)

    def __run(self, argv: list, check: bool = True, **kwargs):
        """Run a seaf-cli command and, unless told otherwise, check its exit
        code. An unchecked failure here surfaces much later as a daemon that
        never becomes ready, with nothing pointing at the real cause."""
        proc = subprocess.run(self.__gen_cmd(argv), **kwargs)
        if check and proc.returncode != 0:
            raise DaemonError(
                f"Command {' '.join(argv)} failed with exit code {proc.returncode}"
            )
        return proc

    def __wait_for_daemon(self, ready: bool, timeout: float, action: str):
        """Wait until the daemon is ready (or stopped), but never forever."""
        deadline = time.monotonic() + timeout
        while self.daemon_ready != ready:
            if time.monotonic() >= deadline:
                state = "ready" if ready else "stopped"
                raise DaemonTimeout(
                    f"Seafile daemon did not become {state} within {timeout}s"
                    f" while {action}"
                )
            time.sleep(const.DAEMON_POLL_PERIOD)

    @property
    def token(self):
        if self.__token is None:
            if not self.password:
                raise ConfigError("No password or token available to authenticate")
            url = f"{self.url}/api2/auth-token/"
            _lg.info("Fetching token: %s", url)
            try:
                r = self.session.post(
                    url,
                    data={"username": self.user, "password": self.password},
                    timeout=const.HTTP_TIMEOUT,
                )
            except requests.exceptions.RequestException as err:
                raise NetworkError(f"Can't reach {url}: {err}") from err
            if r.status_code != 200:
                raise NetworkError(
                    f"Can't get token from {url}: HTTP {r.status_code}: {r.text}"
                )
            self.__token = r.json()["token"]
        return self.__token

    @cached_property_with_ttl(ttl=60)
    def remote_libraries(self) -> dict:
        url = f"{self.url}/api2/repos/"
        _lg.info("Fetching remote libraries: %s", url)
        auth_header = {"Authorization": f"Token {self.token}"}
        try:
            r = self.session.get(url, headers=auth_header, timeout=const.HTTP_TIMEOUT)
        except requests.exceptions.RequestException as err:
            raise NetworkError(f"Can't reach {url}: {err}") from err
        if r.status_code != 200:
            raise NetworkError(f"Can't fetch {url}: HTTP {r.status_code}: {r.text}")
        r_libs = {lib["id"]: lib["name"] for lib in r.json()}
        return r_libs

    @property
    def config_initialized(self) -> bool:
        return os.path.isdir(os.path.join(self.app_dir, ".ccnet"))

    @property
    def daemon_ready(self) -> bool:
        cmd = ["seaf-cli", "status"]
        _lg.info("Checking seafile daemon status: %s", " ".join(cmd))
        proc = subprocess.run(
            self.__gen_cmd(cmd),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return proc.returncode == 0

    def init_config(self):
        if self.config_initialized:
            return
        cmd = ["seaf-cli", "init", "-d", self.app_dir]
        _lg.info("Initializing seafile config: %s", " ".join(cmd))
        self.__run(cmd)

    def start_daemon(self):
        cmd = ["seaf-cli", "start"]
        _lg.info("Starting seafile daemon: %s", " ".join(cmd))
        self.__run(cmd)
        _lg.info("Waiting up to %ss for seafile daemon to start",
                 const.DAEMON_START_TIMEOUT)
        self.__wait_for_daemon(True, const.DAEMON_START_TIMEOUT, "starting")
        _lg.info("Seafile daemon is ready")

    def stop_daemon(self):
        cmd = ["seaf-cli", "stop"]
        _lg.info("Stopping seafile daemon: %s", " ".join(cmd))
        # A daemon that is already gone makes "stop" fail; the state below is
        # what matters, not this exit code.
        self.__run(cmd, check=False)
        _lg.info("Waiting up to %ss for seafile daemon to stop",
                 const.DAEMON_STOP_TIMEOUT)
        self.__wait_for_daemon(False, const.DAEMON_STOP_TIMEOUT, "stopping")
        _lg.info("Seafile daemon is stopped")

    def is_healthy(self) -> bool:
        """
        Report whether the daemon process and its RPC socket both respond.

        Used by the container's HEALTHCHECK. Neither check needs the Seafile
        server, so this works without a token or password.
        """
        if not self.daemon_ready:
            return False
        try:
            self.rpc.get_repo_list(-1, -1)
        except Exception as err:
            _lg.warning("RPC endpoint is not responding: %s", err)
            return False
        return True

    def get_library_id(self, library) -> Optional[str]:
        """
        Resolve a requested name or ID to the one library ID it names.

        Library IDs are unique, but two libraries can share a name. Silently
        matching more than one and picking the first would sync whichever
        happened to come first in the server's response, not necessarily the
        one requested.
        """
        matches = [lib_id for lib_id, lib_name in self.remote_libraries.items()
                   if library in (lib_id, lib_name)]
        if len(matches) > 1:
            raise ConfigError(
                f"{library!r} matches {len(matches)} libraries on the server; "
                "use the library ID instead"
            )
        return matches[0] if matches else None

    def sync_lib(self, lib_id: str, lib_dir: str) -> bool:
        """
        Sync a library into an already resolved directory. The caller decides
        the directory, see dsc.paths.plan_lib_dirs: the name comes from the
        server and must not be turned into a path here.

        Returns whether the library was accepted. One library that cannot be
        synced must not stop the others, so this reports instead of raising.
        """
        create_dir(lib_dir)
        cmd = [
            "seaf-cli",
            "sync",
            "-l", lib_id,
            "-s", self.url,
            "-d", lib_dir,
            "-u", self.user,
            # The token, not the password: seaf-cli ignores the password when a
            # token is given, and command arguments are visible to any process
            # in the container. A token can also be revoked on the server.
            "-T", self.token,
        ]
        _lg.info(
            "Syncing library %s into %s: %s", lib_id, lib_dir,
            " ".join(hide_secrets(cmd, self.token, self.password)),
        )
        proc = self.__run(cmd, check=False)
        if proc.returncode != 0:
            _lg.error("Failed to sync library %s into %s: seaf-cli exited with %s",
                      lib_id, lib_dir, proc.returncode)
            return False
        return True

    def __print_tx_task(self, tx_task) -> str:
        """ Print transfer task status """
        try:
            percentage = tx_task.block_done / tx_task.block_total * 100
            tx_rate = tx_task.rate / 1024.0
            return f" {percentage:.1f}%, {tx_rate:.1f}KB/s"
        except ZeroDivisionError:
            return ""

    def get_status(self) -> dict:
        """ Get status of all libraries """
        statuses = dict()

        # fetch statuses of libraries being cloned
        tasks = self.rpc.get_clone_tasks()
        for clone_task in tasks:
            if clone_task.state == "done":
                continue

            elif clone_task.state == "fetch":
                statuses[clone_task.repo_name] = "downloading"
                tx_task = self.rpc.find_transfer_task(clone_task.repo_id)
                statuses[clone_task.repo_name] += self.__print_tx_task(tx_task)

            elif clone_task.state == "error":
                err = self.rpc.sync_error_id_to_str(clone_task.error)
                statuses[clone_task.repo_name] = f"error: {err}"

            else:
                statuses[clone_task.repo_name] = clone_task.state

        # fetch statuses of synced libraries
        repos = self.rpc.get_repo_list(-1, -1)
        for repo in repos:
            auto_sync_enabled = self.rpc.is_auto_sync_enabled()
            if not auto_sync_enabled or not repo.auto_sync:
                statuses[repo.name] = "auto sync disabled"
                continue

            sync_task = self.rpc.get_repo_sync_task(repo.id)
            if sync_task is None:
                statuses[repo.name] = "waiting for sync"

            elif sync_task.state in ("uploading", "downloading"):
                statuses[repo.name] = sync_task.state
                tx_task = self.rpc.find_transfer_task(repo.id)

                if sync_task.state == "downloading":
                    if tx_task.rt_state == "data":
                        statuses[repo.name] += " files"
                    elif tx_task.rt_state == "fs":
                        statuses[repo.name] += " file list"

                statuses[repo.name] += self.__print_tx_task(tx_task)

            elif sync_task.state == "error":
                err = self.rpc.sync_error_id_to_str(sync_task.error)
                statuses[repo.name] = f"error: {err}"

            else:
                statuses[repo.name] = sync_task.state

        return statuses

    def watch_status(self):
        prev_status = dict()
        max_name_len = 0
        fmt = "Library {:%ds} {}" % max_name_len
        while True:
            time.sleep(const.STATUS_POLL_PERIOD)
            cur_status = self.get_status()
            for library, state in cur_status.items():
                if state != prev_status.get(library):
                    if 30 > len(library) > max_name_len:
                        max_name_len = len(library)
                        fmt = "Library {:%ds}    {}" % max_name_len
                    logging.info(fmt.format(library, state))
                prev_status[library] = cur_status[library]

    def get_local_libraries(self) -> set:
        # The display output is whitespace separated, so a library name or a
        # path containing a space cannot be parsed back apart. Ask for JSON.
        cmd = ["seaf-cli", "list", "--json"]
        _lg.info("Listing local libraries: %s", " ".join(cmd))
        out = self.__run(cmd, stdout=subprocess.PIPE).stdout

        try:
            libraries = json.loads(out.decode())
        except (UnicodeDecodeError, ValueError) as err:
            raise DaemonError(
                f"Cannot read the library list from seaf-cli: {err}"
            ) from err

        # Valid JSON is not necessarily the expected shape, and an unexpected
        # one must fail the same way rather than as a bare TypeError.
        try:
            return {lib["id"] for lib in libraries}
        except (KeyError, TypeError) as err:
            raise DaemonError(
                f"Unexpected library list from seaf-cli: {err}"
            ) from err

    def configure(self, args: argparse.Namespace, check_for_daemon: bool = True):
        need_restart = False
        # Options can be fetched or set only when daemon is running
        if check_for_daemon and not self.daemon_ready:
            self.start_daemon()

        for key, value in args.__dict__.items():
            if key not in const.AVAILABLE_SEAFCLI_OPTIONS:
                continue

            if value is None:
                raise ConfigError(f"No value for seafile option {key}")

            # check current value
            cmd = ["seaf-cli", "config", "-k", key]
            _lg.info("Checking seafile client option: %s", " ".join(cmd))
            proc = self.__run(cmd, stdout=subprocess.PIPE)
            # stdout looks like "option = value"
            cur_value = proc.stdout.decode().strip()
            try:
                cur_value = cur_value.split(sep="=")[1].strip()
            except IndexError:
                cur_value = None
            if cur_value == config_value(value):
                continue

            # set new value
            cmd = ["seaf-cli", "config", "-k", key, "-v", config_value(value)]
            _lg.info("Setting seafile client option: %s", " ".join(cmd))
            self.__run(cmd)
            need_restart = True

        if need_restart:
            _lg.info("Restarting seafile daemon")
            self.stop_daemon()
            self.start_daemon()
