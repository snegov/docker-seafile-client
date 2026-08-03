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
    Return a command as-is, having already validated it is a plain argument
    list and never a shell string.

    The process itself runs as the seafile user for its whole life after
    drop_privileges() (see start.py), so subprocess calls no longer need to
    be individually re-targeted with ``runuser``.
    """
    if not isinstance(argv, list):
        raise TypeError(f"Command must be a list of arguments, got {type(argv).__name__}")
    return argv


def drop_privileges(uid: int, gid: int):
    """
    Permanently switch the current process to the given UID/GID.

    Must run after setup_uid()/create_dir(), which need root, and before any
    other code, since everything from here on (the daemon, the RPC socket,
    the sync loop) runs as this user for the rest of the process's life.
    Order matters: supplementary groups and the GID must be set before the
    UID is dropped, since giving up root removes the permission to change
    them.
    """
    user_pwinfo = pwd.getpwnam(DEFAULT_USERNAME)
    os.initgroups(DEFAULT_USERNAME, gid)
    os.setgid(gid)
    os.setuid(uid)
    os.environ["HOME"] = user_pwinfo.pw_dir
    os.environ["USER"] = DEFAULT_USERNAME
    os.environ["LOGNAME"] = DEFAULT_USERNAME


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
