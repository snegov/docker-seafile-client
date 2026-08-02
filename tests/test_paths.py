import os

import pytest

from dsc.paths import UnsafeLibraryName, lib_dirname, plan_lib_dirs, resolve_lib_dir

PARENT = "/dsc/seafile"


@pytest.mark.parametrize("name, expected", [
    ("Documents", "Documents"),
    ("My Library", "My_Library"),
    ("  padded  ", "padded"),
    ("Ünïcödé ☂", "Ünïcödé_☂"),
    # The characters below used to reach a shell. They are now ordinary
    # filename characters and must survive untouched.
    ('quote"name', 'quote"name'),
    ("single'name", "single'name"),
    ("semi;colon", "semi;colon"),
    ("dollar$(id)", "dollar$(id)"),
    ("back`id`tick", "back`id`tick"),
    ("pipe|amp&name", "pipe|amp&name"),
    ("new\nline", "new_line"),
    ("tab\tname", "tab_name"),
    ("dash-lead", "dash-lead"),
    ("-leading-dash", "-leading-dash"),
])
def test_lib_dirname_accepts(name, expected):
    assert lib_dirname(name) == expected


@pytest.mark.parametrize("name", [
    "",
    "   ",
    "\n",
    ".",
    "..",
    "...",  # not special to the kernel, but never a library name we want
    "/",
    "/etc",
    "/etc/passwd",
    "../escape",
    "../../root",
    "nested/name",
    "trailing/",
    "nul\0byte",
])
def test_lib_dirname_rejects(name):
    with pytest.raises(UnsafeLibraryName):
        lib_dirname(name)


def test_resolve_lib_dir_stays_under_parent():
    assert resolve_lib_dir(PARENT, "Documents") == "/dsc/seafile/Documents"


def test_resolve_lib_dir_rejects_escape_through_symlink(tmp_path):
    parent = tmp_path / "seafile"
    parent.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (parent / "escape").symlink_to(outside)

    with pytest.raises(UnsafeLibraryName):
        resolve_lib_dir(str(parent), "escape")


def test_resolve_lib_dir_allows_real_dir_under_parent(tmp_path):
    parent = tmp_path / "seafile"
    parent.mkdir()
    (parent / "Documents").mkdir()

    resolved = resolve_lib_dir(str(parent), "Documents")
    assert resolved == os.path.realpath(str(parent / "Documents"))


def test_plan_lib_dirs_maps_each_library_to_its_own_dir():
    plan = plan_lib_dirs({"id-a": "Docs", "id-b": "My Photos"}, PARENT)
    assert plan == {
        "id-a": "/dsc/seafile/Docs",
        "id-b": "/dsc/seafile/My_Photos",
    }


def test_plan_lib_dirs_disambiguates_duplicate_names():
    libs = {"aaaaaaaabbbb": "Docs", "ccccccccdddd": "Docs"}
    plan = plan_lib_dirs(libs, PARENT)

    assert plan == {
        "aaaaaaaabbbb": "/dsc/seafile/Docs-aaaaaaaa",
        "ccccccccdddd": "/dsc/seafile/Docs-cccccccc",
    }


def test_plan_lib_dirs_duplicate_suffix_is_order_independent():
    libs = {"aaaaaaaabbbb": "Docs", "ccccccccdddd": "Docs"}
    reversed_libs = dict(reversed(list(libs.items())))
    assert plan_lib_dirs(libs, PARENT) == plan_lib_dirs(reversed_libs, PARENT)


def test_plan_lib_dirs_duplicates_collide_after_space_folding():
    """'A B' and 'A_B' both fold to 'A_B' and must not share a directory."""
    libs = {"aaaaaaaabbbb": "A B", "ccccccccdddd": "A_B"}
    plan = plan_lib_dirs(libs, PARENT)
    assert len(set(plan.values())) == 2


def test_plan_lib_dirs_skips_unsafe_names_and_keeps_the_rest():
    libs = {"good": "Docs", "bad": "../escape"}
    plan = plan_lib_dirs(libs, PARENT)
    assert plan == {"good": "/dsc/seafile/Docs"}
