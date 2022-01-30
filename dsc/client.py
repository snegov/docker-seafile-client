import logging
import os
import subprocess
import time
from typing import Optional
from urllib.parse import urlparse

from cached_property import cached_property_with_ttl
import requests

from dsc import consts
from dsc.misc import create_dir

_lg = logging.getLogger(__name__)


class SeafileClient:
    def __init__(self, host: str, user: str, passwd: str):
        up = urlparse(requests.get(f"http://{host}").url)
        self.url = f"{up.scheme}://{up.netloc}"
        self.user = user
        self.password = passwd
        self.__token = None

    def __str__(self):
        return f"SeafileClient({self.user}@{self.url})"

    @property
    def token(self):
        if self.__token is None:
            url = f"{self.url}/api2/auth-token/"
            r = requests.post(url, data={"username": self.user,
                                         "password": self.password})
            if r.status_code != 200:
                raise RuntimeError(f"Can't get token: {r.text}")
            self.__token = r.json()['token']
        return self.__token

    @cached_property_with_ttl(ttl=60)
    def remote_libraries(self) -> dict:
        url = f"{self.url}/api2/repos/"
        auth_header = {"Authorization": f"Token {self.token}"}
        r = requests.get(url, headers=auth_header)
        if r.status_code != 200:
            raise RuntimeError(r.text)
        r_libs = {lib["id"]: lib["name"] for lib in r.json()}
        return r_libs

    def get_library_id(self, library) -> Optional[str]:
        for lib_id, lib_name in self.remote_libraries.items():
            if library in (lib_id, lib_name):
                return lib_id
        return None

    def sync_lib(self, lib_id: str, data_dir: str):
        lib_name = self.remote_libraries[lib_id]
        lib_dir = os.path.join(data_dir, lib_name.replace(' ', '_'))
        create_dir(lib_dir)
        cmd = ['seaf-cli', 'sync',
               '-l', lib_id,
               '-s', self.url,
               '-d', lib_dir,
               '-u', self.user,
               '-p', self.password]
        cmd = ' '.join(cmd)
        subprocess.run(['su', '-', consts.DEFAULT_USERNAME, '-c', cmd])

    def get_status(self):
        cmd = 'seaf-cli status'
        out = subprocess.check_output(['su', '-', consts.DEFAULT_USERNAME, '-c', cmd])
        out = out.decode().splitlines()

        statuses = dict()
        for line in out:
            if line.startswith('#') or not line.strip():
                continue
            lib, status = line.split(sep='\t', maxsplit=1)
            lib = lib.strip()
            status = " ".join(status.split())
            statuses[lib] = status
        return statuses

    def watch_status(self):
        prev_status = dict()
        while True:
            time.sleep(consts.STATUS_POLL_PERIOD)
            cur_status = self.get_status()
            for folder, state in cur_status.items():
                if state != prev_status.get(folder):
                    logging.info("Library %s:\t%s", folder, state)
                prev_status[folder] = cur_status[folder]

    def get_local_libraries(self) -> set:
        cmd = 'seaf-cli list'
        out = subprocess.check_output(['su', '-', consts.DEFAULT_USERNAME, '-c', cmd])
        out = out.decode().splitlines()[1:]     # first line is a header

        local_libs = set()
        for line in out:
            lib_name, lib_id, lib_path = line.rsplit(maxsplit=3)
            local_libs.add(lib_id)
        return local_libs


def start_seaf_daemon():
    cmd = 'seaf-cli start'
    subprocess.run(['su', '-', consts.DEFAULT_USERNAME, '-c', cmd])
