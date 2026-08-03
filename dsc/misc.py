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


def user_cmd(argv: list) -> list:
    """
    Wrap a command so that it runs as the seafile user.

    ``runuser --`` execs the command directly. ``su -c`` would hand it to a
    login shell instead, which turns every server-provided value in the
    command into shell code. Like ``su``, ``runuser`` sets HOME, USER and a
    default PATH for the target user, so seaf-cli still finds its config and
    its own wrapper.
    """
    if not isinstance(argv, list):
        raise TypeError(f"Command must be a list of arguments, got {type(argv).__name__}")
    return ["runuser", "-u", DEFAULT_USERNAME, "--"] + argv


def hide_secrets(cmd: list, *secrets: str) -> list:
    """Mask every given secret in a command before it is logged."""
    cmd = cmd.copy()
    for secret in secrets:
        if not secret:
            continue
        for i, arg in enumerate(cmd):
            if secret in arg:
                cmd[i] = arg.replace(secret, "********")
    return cmd


def config_value(value) -> str:
    """
    Render a setting the way seaf-cli stores it.

    Booleans are written as "true" and "false": the daemon reads this setting
    with its boolean accessor, and Python's str() would produce "True".
    """
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)
