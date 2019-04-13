#!/usr/bin/env python3

import argparse
import os
import os.path
import pwd
import subprocess
import sys
import time

import requests

DEFAULT_USERNAME = "seafile"


def setup_uid(uid: int, gid: int):
    user_pwinfo = pwd.getpwnam(DEFAULT_USERNAME)
    if user_pwinfo.pw_uid != uid or user_pwinfo.pw_gid != gid:
        subprocess.call(["usermod", "-o", "-u", str(uid), "-g", str(gid), DEFAULT_USERNAME])


def start_seaf_daemon():
    os.system(f'su - {DEFAULT_USERNAME} -c "seaf-cli start"')
    time.sleep(10)


def create_dir(dir_path: str):
    if not os.path.exists(dir_path):
        os.mkdir(dir_path)
        user_pwinfo = pwd.getpwnam(DEFAULT_USERNAME)
        os.chown(dir_path, user_pwinfo.pw_uid, user_pwinfo.pw_gid)
    else:
        if not os.path.isdir(dir_path):
            raise RuntimeError(f"Data dir {dir_path} is not a directory")


def tail_f(fpath):
    os.system(f"tail -f {fpath}")


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
        os.system(f'su - {DEFAULT_USERNAME} -c "{cmd}"')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--uid", default=os.getenv("SEAFILE_UID"), type=int)
    parser.add_argument("--gid", default=os.getenv("SEAFILE_GID"), type=int)
    parser.add_argument("--data-dir", default=os.getenv("DATA_DIR"))
    parser.add_argument("--host", default=os.getenv("SERVER_HOST"))
    parser.add_argument("--port", default=os.getenv("SERVER_PORT"), type=int)
    parser.add_argument("--username", default=os.getenv("USERNAME"))
    parser.add_argument("--password", default=os.getenv("PASSWORD"))
    parser.add_argument("--libs", default=os.getenv("LIBRARY_ID"))
    args = parser.parse_args()

    setup_uid(args.uid, args.gid)
    start_seaf_daemon()
    create_dir(args.data_dir)
    client = SeafileClient(args.host, args.port, args.username, args.password)
    for lib_id in args.libs.split(sep=":"):
        client.sync_lib(lib_id, args.data_dir)
    tail_f("/seafile-client/.ccnet/logs/seafile.log")

    return 0


if __name__ == "__main__":
    sys.exit(main())
