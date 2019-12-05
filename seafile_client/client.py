import logging
import os
import subprocess
import time

import requests

from .consts import DEFAULT_USERNAME
from .misc import create_dir


logging.basicConfig(format="%(asctime)s %(message)s",
                    level=logging.INFO)


class SeafileClient:
    def __init__(self, host: str, port: int, user: str, passwd: str):
        self.url = f"https://{host}:{port}"
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

    def get_lib_name(self, lib_id: str) -> str:
        url = f"{self.url}/api2/repos/{lib_id}"
        auth_header = {"Authorization": f"Token {self.token}"}
        r = requests.get(url, headers=auth_header)
        if r.status_code != 200:
            raise RuntimeError(r.text)
        return r.json()['name']

    def sync_lib(self, lib_id: str, data_dir: str):
        lib_name = self.get_lib_name(lib_id)
        lib_dir = os.path.join(data_dir, lib_name.replace(' ', '_'))
        create_dir(lib_dir)
        cmd = ['seaf-cli', 'sync',
               '-l', lib_id,
               '-s', self.url,
               '-d', lib_dir,
               '-u', self.user,
               '-p', self.password]
        cmd = ' '.join(cmd)
        subprocess.run(['su', '-', DEFAULT_USERNAME, '-c', cmd])

    def get_status(self):
        cmd = 'seaf-cli status'
        out = subprocess.check_output(['su', '-', DEFAULT_USERNAME, '-c', cmd])
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
            time.sleep(5)
            cur_status = self.get_status()
            for folder, state in cur_status.items():
                if state != prev_status.get(folder):
                    logging.info(f"Library {folder}:\t{state}")
                prev_status[folder] = cur_status[folder]


def start_seaf_daemon():
    cmd = 'seaf-cli start'
    subprocess.run(['su', '-', DEFAULT_USERNAME, '-c', cmd])
    time.sleep(5)
