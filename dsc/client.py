import argparse
import logging
import os
import subprocess
import time
from typing import Optional
from urllib.parse import urlparse

from cached_property import cached_property_with_ttl
import requests
import seafile

from dsc import const
from dsc.misc import create_dir, hide_password

_lg = logging.getLogger(__name__)


class SeafileClient:
    def __init__(self,
                 host: str,
                 user: str,
                 passwd: str,
                 app_dir: str = const.DEFAULT_APP_DIR):
        # check if host supports https
        up = urlparse(requests.get(f"http://{host}").url)
        self.url = f"{up.scheme}://{up.netloc}"
        self.user = user
        self.password = passwd
        self.app_dir = os.path.abspath(app_dir)
        self.rpc = seafile.RpcClient(os.path.join(self.app_dir, 'seafile-data', 'seafile.sock'))
        self.__token = None

    def __str__(self):
        return f"SeafileClient({self.user}@{self.url})"

    def __gen_cmd(self, cmd: str) -> list:
        return ["su", "-", const.DEFAULT_USERNAME, "-c", cmd]

    @property
    def token(self):
        if self.__token is None:
            url = f"{self.url}/api2/auth-token/"
            _lg.info("Fetching token: %s", url)
            r = requests.post(url, data={"username": self.user, "password": self.password})
            if r.status_code != 200:
                raise RuntimeError(f"Can't get token: {r.text}")
            self.__token = r.json()["token"]
        return self.__token

    @cached_property_with_ttl(ttl=60)
    def remote_libraries(self) -> dict:
        url = f"{self.url}/api2/repos/"
        _lg.info("Fetching remote libraries: %s", url)
        auth_header = {"Authorization": f"Token {self.token}"}
        r = requests.get(url, headers=auth_header)
        if r.status_code != 200:
            raise RuntimeError(r.text)
        r_libs = {lib["id"]: lib["name"] for lib in r.json()}
        return r_libs

    @property
    def config_initialized(self) -> bool:
        return os.path.isdir(os.path.join(self.app_dir, ".ccnet"))

    @property
    def daemon_ready(self) -> bool:
        cmd = "seaf-cli status"
        _lg.info("Checking seafile daemon status: %s", cmd)
        proc = subprocess.run(
            self.__gen_cmd(cmd),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return proc.returncode == 0

    def init_config(self):
        if self.config_initialized:
            return
        cmd = "seaf-cli init -d %s" % self.app_dir
        _lg.info("Initializing seafile config: %s", cmd)
        subprocess.run(self.__gen_cmd(cmd))

    def start_daemon(self):
        cmd = "seaf-cli start"
        _lg.info("Starting seafile daemon: %s", cmd)
        subprocess.run(self.__gen_cmd(cmd))
        _lg.info("Waiting for seafile daemon to start")

        while True:
            if self.daemon_ready:
                break
            time.sleep(5)

        _lg.info("Seafile daemon is ready")

    def stop_daemon(self):
        cmd = "seaf-cli stop"
        _lg.info("Stopping seafile daemon: %s", cmd)
        subprocess.run(self.__gen_cmd(cmd))
        _lg.info("Waiting for seafile daemon to stop")

        while True:
            if not self.daemon_ready:
                break
            time.sleep(5)

        _lg.info("Seafile daemon is stopped")

    def get_library_id(self, library) -> Optional[str]:
        for lib_id, lib_name in self.remote_libraries.items():
            if library in (lib_id, lib_name):
                return lib_id
        return None

    def sync_lib(self, lib_id: str, parent_dir: str = const.DEFAULT_LIBS_DIR):
        lib_name = self.remote_libraries[lib_id]
        lib_dir = os.path.join(parent_dir, lib_name.replace(" ", "_"))
        create_dir(lib_dir)
        cmd = [
            "seaf-cli",
            "sync",
            "-l", lib_id,
            "-s", self.url,
            "-d", lib_dir,
            "-u", self.user,
            "-p", '"' + self.password + '"',
        ]
        _lg.info(
            "Syncing library %s: %s", lib_name,
            " ".join(hide_password(cmd, self.password)),
        )
        subprocess.run(self.__gen_cmd(" ".join(cmd)))

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
        while True:
            time.sleep(const.STATUS_POLL_PERIOD)
            cur_status = self.get_status()
            for folder, state in cur_status.items():
                if state != prev_status.get(folder):
                    logging.info("Library %s:\t%s", folder, state)
                prev_status[folder] = cur_status[folder]

    def get_local_libraries(self) -> set:
        cmd = "seaf-cli list"
        _lg.info("Listing local libraries: %s", cmd)
        out = subprocess.check_output(self.__gen_cmd(cmd))
        out = out.decode().splitlines()[1:]  # first line is a header

        local_libs = set()
        for line in out:
            lib_name, lib_id, lib_path = line.rsplit(maxsplit=3)
            local_libs.add(lib_id)
        return local_libs

    def configure(self, args: argparse.Namespace, check_for_daemon: bool = True):
        need_restart = False
        # Options can be fetched or set only when daemon is running
        if check_for_daemon and not self.daemon_ready:
            self.start_daemon()

        for key, value in args.__dict__.items():
            if key not in const.AVAILABLE_SEAFCLI_OPTIONS:
                continue

            # check current value
            cmd = f"seaf-cli config -k {key}"
            _lg.info("Checking seafile client option: %s", cmd)
            proc = subprocess.run(self.__gen_cmd(cmd), stdout=subprocess.PIPE)
            # stdout looks like "option = value"
            cur_value = proc.stdout.decode().strip()
            try:
                cur_value = cur_value.split(sep="=")[1].strip()
            except IndexError:
                cur_value = None
            if cur_value == str(value):
                continue

            # set new value
            cmd = f"seaf-cli config -k {key} -v {value}"
            _lg.info("Setting seafile client option: %s", cmd)
            subprocess.run(self.__gen_cmd(cmd))
            need_restart = True

        if need_restart:
            _lg.info("Restarting seafile daemon")
            self.stop_daemon()
            self.start_daemon()
