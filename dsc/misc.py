import os
import pwd
import subprocess

from dsc.consts import DEFAULT_USERNAME


def setup_uid(uid: int, gid: int):
    user_pwinfo = pwd.getpwnam(DEFAULT_USERNAME)
    if user_pwinfo.pw_uid != uid or user_pwinfo.pw_gid != gid:
        subprocess.call(["usermod", "-o", "-u", str(uid), "-g", str(gid), DEFAULT_USERNAME])


def create_dir(dir_path: str):
    if not os.path.exists(dir_path):
        os.mkdir(dir_path)
        user_pwinfo = pwd.getpwnam(DEFAULT_USERNAME)
        os.chown(dir_path, user_pwinfo.pw_uid, user_pwinfo.pw_gid)
    else:
        if not os.path.isdir(dir_path):
            raise RuntimeError(f"Data dir {dir_path} is not a directory")


def hide_password(cmd: list, password: str) -> list:
    cmd = cmd.copy()
    for i, arg in enumerate(cmd):
        if arg == password:
            cmd[i] = '********'
    return cmd
