"""Turn server-provided library names into safe local directories.

Library names come from the Seafile server and are untrusted: a name is chosen
by whoever can create a library, and it must never decide where the container
writes. Every name is reduced to a single path component and every resulting
path is proven to stay under the libraries directory.
"""

import logging
import os
from collections import Counter

_lg = logging.getLogger(__name__)

# Whitespace is folded into underscores so that library names survive as
# readable directory names, as they always have.
_WHITESPACE_REPLACEMENT = "_"

# Names that are not usable as a directory of their own.
_RESERVED_NAMES = {"", ".", "..", "..."}

# Length of the library id used to break ties between duplicate names.
_ID_SUFFIX_LEN = 8


class UnsafeLibraryName(ValueError):
    """A library name cannot be mapped to a directory under the parent."""


def lib_dirname(lib_name: str) -> str:
    """
    Return the directory name for a library, or raise for a name that cannot
    be one. Shell metacharacters are ordinary filename characters here: nothing
    reaches a shell any more, so they are kept rather than mangled.
    """
    if not isinstance(lib_name, str):
        raise UnsafeLibraryName(f"Library name is not a string: {lib_name!r}")

    name = "".join(
        _WHITESPACE_REPLACEMENT if ch.isspace() else ch
        for ch in lib_name.strip()
    )

    if "\0" in name:
        raise UnsafeLibraryName("Library name contains a null byte")
    if os.sep in name or (os.altsep and os.altsep in name):
        raise UnsafeLibraryName(f"Library name contains a path separator: {lib_name!r}")
    if name in _RESERVED_NAMES:
        raise UnsafeLibraryName(f"Library name is not usable as a directory: {lib_name!r}")

    return name


def resolve_lib_dir(parent_dir: str, dir_name: str) -> str:
    """
    Resolve ``dir_name`` inside ``parent_dir`` and prove that the result stays
    there. Symlinks are resolved first, so an existing symlink inside the
    parent cannot be used to write outside it.
    """
    parent = os.path.realpath(parent_dir)
    resolved = os.path.realpath(os.path.join(parent, dir_name))

    if resolved != parent and not resolved.startswith(parent + os.sep):
        raise UnsafeLibraryName(
            f"Library directory {resolved} is outside {parent}"
        )
    if resolved == parent:
        raise UnsafeLibraryName(f"Library directory resolves to {parent} itself")

    return resolved


def plan_lib_dirs(libraries: dict, parent_dir: str) -> dict:
    """
    Map library id to its directory for every library that can safely have one.

    Libraries whose names collide after whitespace folding would otherwise
    share a directory and corrupt each other, so each of them is suffixed with
    the start of its own id. Unsafe names are skipped with a warning rather
    than aborting the sync of the remaining libraries.
    """
    names = dict()
    for lib_id, lib_name in libraries.items():
        try:
            names[lib_id] = lib_dirname(lib_name)
        except UnsafeLibraryName as err:
            _lg.warning("Skipping library %s: %s", lib_id, err)

    counts = Counter(names.values())
    duplicates = {name for name, count in counts.items() if count > 1}

    plan = dict()
    for lib_id, name in names.items():
        if name in duplicates:
            name = f"{name}-{lib_id[:_ID_SUFFIX_LEN]}"
        try:
            plan[lib_id] = resolve_lib_dir(parent_dir, name)
        except UnsafeLibraryName as err:
            _lg.warning("Skipping library %s: %s", lib_id, err)

    return plan
