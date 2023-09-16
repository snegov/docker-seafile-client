import os
import pwd
import subprocess

from dsc.const import DEFAULT_USERNAME


def setup_uid(uid: int, gid: int):
    """
    Set GID and UID of default user so that seafile client creates files with
    correct permissions.
    If GID does not match, create a new group with the given GID.
    Then update UID and GID of default user to match the given ones.
    """
    user_pwinfo = pwd.getpwnam(DEFAULT_USERNAME)
    create_group(gid)
    if user_pwinfo.pw_uid != uid or user_pwinfo.pw_gid != gid:
        subprocess.call(["usermod", "-o", "-u", str(uid), "-g", str(gid), DEFAULT_USERNAME])


def create_group(gid: int):
    """Search for a group with the given GID. If not found, create a new one."""
    if not os.path.exists(f"/etc/group"):
        raise RuntimeError(f"File /etc/group does not exist")
    with open("/etc/group", "r") as f:
        for line in f.readlines():
            cur_gid = line.split(sep=":", maxsplit=3)[2]
            if int(cur_gid) == gid:
                return
    subprocess.call(["groupadd", "-g", str(gid), DEFAULT_USERNAME + "-data"])


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
