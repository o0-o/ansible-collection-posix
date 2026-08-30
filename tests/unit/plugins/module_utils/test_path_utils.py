# vim: ts=4:sw=4:sts=4:et:ft=python
# -*- mode: python; tab-width: 4; indent-tabs-mode: nil; -*-
#
# GNU General Public License v3.0+
# SPDX-License-Identifier: GPL-3.0-or-later
# (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
#
# Copyright (c) 2025 oØ.o (@o0-o)
#
# This file is part of the o0_o.posix Ansible Collection.

"""Unit tests for the o0_paths composer in path_utils."""

from __future__ import annotations

from typing import Any

import pytest

from ansible_collections.o0_o.posix.plugins.module_utils.path_utils import (
    canonicalize,
    compose_paths,
    normalize_mode,
)

# One observation's worth of facts about a path, as a producer that
# read metadata would hand them over
SH = {
    "type": "regular",
    "mode": "0755",
    "uid": 0,
    "gid": 0,
}


def test_compose_paths_with_nothing_observed() -> None:
    """Test that composing nothing yields an empty store."""

    assert compose_paths() == {}
    assert compose_paths(None, None) == {}


def test_compose_paths_validates_a_lone_observation() -> None:
    """Test that a producer can compose its own answer alone."""

    assert compose_paths({"/bin/sh": SH}) == {"/bin/sh": SH}


@pytest.mark.parametrize(
    "path",
    [
        "/",
        "/bin/sh",
        "/etc/.pwd.lock",
        "/etc/..bashrc",
        "/home/o0-o/~backup",
        "/home/o0-o/Application Support",
        "/usr/local/...",
    ],
)
def test_compose_paths_accepts_absolute_keys(path: str) -> None:
    """Test that any absolute, canonical path keys the store."""

    assert compose_paths({path: {}}) == {path: {}}


@pytest.mark.parametrize(
    "path, error_text",
    [
        ("bin/sh", "must be an absolute path"),
        ("./bin/sh", "must be an absolute path"),
        ("../bin/sh", "must be an absolute path"),
        ("~", "must be an absolute path"),
        ("~/.ssh/config", "must be an absolute path"),
        ("", "must not be empty"),
        ("/usr/bin/", "must not end in '/'"),
        ("/usr//bin/sh", "must not contain an empty path component"),
        ("/usr/./bin/sh", "must be canonical"),
        ("/usr/bin/../sh", "must be canonical"),
    ],
)
def test_compose_paths_rejects_keys_that_are_not_flat_paths(
    path: str, error_text: str
) -> None:
    """Test that a key that is not one flat absolute path raises."""

    with pytest.raises(ValueError, match=error_text):
        compose_paths({path: {}})


@pytest.mark.parametrize("path", [1, None, ("/bin/sh",)])
def test_compose_paths_rejects_keys_that_are_not_strings(
    path: Any,
) -> None:
    """Test that a non-string key raises rather than stringifying."""

    with pytest.raises(ValueError, match="must be a string"):
        compose_paths({path: {}})


def test_compose_paths_names_the_argument_a_bad_key_came_from() -> None:
    """Test that the message says which mapping was malformed."""

    with pytest.raises(ValueError, match="key in the store"):
        compose_paths({"bin/sh": {}}, {})

    with pytest.raises(ValueError, match="key in the observation"):
        compose_paths({}, {"bin/sh": {}})


@pytest.mark.parametrize(
    "source",
    ["/bin/sh", ["/bin/sh"], 0, {"/bin/sh"}],
)
def test_compose_paths_rejects_a_store_that_is_not_a_mapping(
    source: Any,
) -> None:
    """Test that only a path-keyed mapping composes."""

    with pytest.raises(ValueError, match="must be a mapping of paths"):
        compose_paths(source)

    with pytest.raises(ValueError, match="must be a mapping of paths"):
        compose_paths(None, source)


@pytest.mark.parametrize(
    "entry",
    ["regular", ["regular"], 0, True],
)
def test_compose_paths_rejects_entries_that_are_not_facts(
    entry: Any,
) -> None:
    """Test that an entry is either observed facts or a null."""

    with pytest.raises(ValueError, match="must be a mapping of"):
        compose_paths({"/bin/sh": entry})


def test_compose_paths_rejects_a_path_store_under_an_entry() -> None:
    """Test that an entry keyed by a path is refused as nesting."""

    nested = {"/etc": {"type": "directory", "/etc/passwd": SH}}

    with pytest.raises(ValueError, match="The store is flat"):
        compose_paths(nested)


def test_compose_paths_rejects_a_field_that_is_not_a_string() -> None:
    """Test that an entry's field names are strings."""

    with pytest.raises(ValueError, match="which is not a string"):
        compose_paths({"/bin/sh": {0: "regular"}})


def test_compose_paths_takes_children_as_path_references() -> None:
    """Test that a directory names its contents as path strings."""

    listing = {
        "/etc": {
            "type": "directory",
            "children": ["/etc/passwd", "/etc/shells"],
        }
    }

    assert compose_paths(listing) == listing


def test_compose_paths_takes_an_empty_directory_listing() -> None:
    """Test that an empty children list means an empty directory."""

    listing = {"/var/empty": {"type": "directory", "children": []}}

    assert compose_paths(listing)["/var/empty"]["children"] == []


@pytest.mark.parametrize(
    "children, error_text",
    [
        (
            [{"/etc/passwd": SH}],
            "must be a string",
        ),
        (
            [{"path": "/etc/passwd"}],
            "must be a string",
        ),
        (
            {"/etc/passwd": SH},
            "must be a list of path references",
        ),
        (
            "/etc/passwd",
            "must be a list of path references",
        ),
        (
            ["passwd", "shells"],
            "must be an absolute path",
        ),
    ],
)
def test_compose_paths_rejects_children_that_are_not_references(
    children: Any, error_text: str
) -> None:
    """Test that a directory cannot carry its children's entries."""

    with pytest.raises(ValueError, match=error_text):
        compose_paths({"/etc": {"children": children}})


def test_compose_paths_names_the_directory_a_bad_child_came_from() -> None:
    """Test that a bad child reference names its directory."""

    with pytest.raises(ValueError, match="children reference of '/etc'"):
        compose_paths({"/etc": {"children": ["passwd"]}})


def test_compose_paths_newest_observation_wins() -> None:
    """Test that a re-observed path takes the newer entry."""

    store = {"/bin/sh": {"type": "regular", "mode": "0755"}}
    observation = {"/bin/sh": {"type": "regular", "mode": "0644"}}

    composed = compose_paths(store, observation)

    assert composed["/bin/sh"]["mode"] == "0644"


def test_compose_paths_newest_observation_wins_whole() -> None:
    """Test that fields are not blended across observations."""

    store = {"/bin/sh": SH}
    observation = {"/bin/sh": {"type": "regular"}}

    composed = compose_paths(store, observation)

    assert composed["/bin/sh"] == {"type": "regular"}
    assert "mode" not in composed["/bin/sh"]


def test_compose_paths_null_overwrites_a_known_path() -> None:
    """Test that a re-observed missing path records the deletion."""

    store = {"/etc/nologin": {"type": "regular"}, "/bin/sh": SH}

    composed = compose_paths(store, {"/etc/nologin": None})

    assert composed["/etc/nologin"] is None
    assert composed["/bin/sh"] == SH


def test_compose_paths_an_entry_resurrects_a_null_path() -> None:
    """Test that a path observed again overwrites its null."""

    composed = compose_paths({"/etc/nologin": None}, {"/etc/nologin": SH})

    assert composed["/etc/nologin"] == SH


def test_compose_paths_leaves_paths_the_observation_never_asked() -> None:
    """Test that an unmentioned path keeps the entry it had."""

    store = {"/bin/sh": SH, "/etc/passwd": None}

    composed = compose_paths(store, {"/bin/cat": {"type": "regular"}})

    assert composed["/bin/sh"] == SH
    assert composed["/etc/passwd"] is None
    assert composed["/bin/cat"] == {"type": "regular"}


def test_compose_paths_never_asked_stays_absent() -> None:
    """Test that composing invents no keys for unasked paths."""

    composed = compose_paths({"/bin/sh": SH}, {"/bin/cat": None})

    assert set(composed) == {"/bin/sh", "/bin/cat"}
    assert "/bin/zsh" not in composed


def test_compose_paths_keeps_a_null_out_of_an_empty_mapping() -> None:
    """Test that null and the empty mapping are not interchanged."""

    composed = compose_paths({"/bin/sh": None, "/bin/cat": {}})

    assert composed["/bin/sh"] is None
    assert composed["/bin/cat"] == {}


@pytest.mark.parametrize(
    "field, value",
    [
        ("target", ""),
        ("children", []),
        ("acl", {}),
        ("flags", []),
        ("content", ""),
    ],
)
def test_compose_paths_passes_typed_empties_through(
    field: str, value: Any
) -> None:
    """Test that a typed empty survives composition unchanged."""

    composed = compose_paths({"/bin/sh": {field: value}})

    assert composed["/bin/sh"][field] == value
    assert composed["/bin/sh"][field] is not None


def test_compose_paths_keeps_an_empty_entry_apart_from_a_null() -> None:
    """Test that an empty entry is a path that exists."""

    composed = compose_paths(
        {"/bin/sh": SH},
        {"/bin/sh": {}, "/bin/ksh": None},
    )

    assert composed["/bin/sh"] == {}
    assert composed["/bin/ksh"] is None


def test_compose_paths_does_not_write_back_to_its_arguments() -> None:
    """Test that composing leaves the mappings it was handed."""

    store = {"/bin/sh": {"type": "regular"}}
    observation = {"/etc": {"children": ["/etc/passwd"]}}

    composed = compose_paths(store, observation)
    composed["/bin/sh"]["mode"] = "0755"
    composed["/etc"]["children"].append("/etc/shells")
    composed["/bin/cat"] = None

    assert store == {"/bin/sh": {"type": "regular"}}
    assert observation == {"/etc": {"children": ["/etc/passwd"]}}


def test_compose_paths_accumulates_across_producers() -> None:
    """Test that a store composes forward one observation at a time."""

    store = compose_paths(None, {"/bin/sh": {}})
    store = compose_paths(store, {"/bin/sh": SH, "/etc/shells": None})
    store = compose_paths(
        store,
        {"/etc/shells": {"type": "regular"}, "/bin/cat": None},
    )

    assert store == {
        "/bin/sh": SH,
        "/etc/shells": {"type": "regular"},
        "/bin/cat": None,
    }


@pytest.mark.parametrize(
    "path, canonical",
    [
        ("/", "/"),
        ("//", "/"),
        ("///usr/bin", "/usr/bin"),
        ("/usr/bin", "/usr/bin"),
        ("/usr/bin/", "/usr/bin"),
        ("/usr//bin", "/usr/bin"),
        ("/usr/./bin", "/usr/bin"),
        ("/usr/local/../bin", "/usr/bin"),
        ("/usr/bin/..", "/usr"),
        ("/..", "/"),
        ("/srv/~/bin", "/srv/~/bin"),
        ("/srv/Application Support", "/srv/Application Support"),
    ],
)
def test_canonicalize_reduces_a_path_to_the_key_the_store_uses(
    path: str, canonical: str
) -> None:
    """Test that a path keys the store by what it is rather than by
    how it was written."""

    assert canonicalize(path) == canonical


@pytest.mark.parametrize(
    "path",
    [
        "/",
        "/usr/bin",
        "/srv/~/bin",
    ],
)
def test_canonicalize_leaves_a_key_the_store_takes_alone(
    path: str,
) -> None:
    """Test that canonicalizing what is already a key changes
    nothing, so a producer may canonicalize whatever it holds."""

    assert canonicalize(canonicalize(path)) == canonicalize(path)
    assert compose_paths(None, {canonicalize(path): None}) == {path: None}


@pytest.mark.parametrize(
    "path",
    [
        "/usr/bin/",
        "/usr//bin",
        "/usr/./bin",
        "/usr/local/../bin",
        "//usr/bin",
    ],
)
def test_canonicalize_repairs_what_the_store_refuses(path: str) -> None:
    """Test that every spelling compose_paths refuses is a spelling
    canonicalize turns into one it takes.  The two are meant to be
    used that way round: a producer canonicalizes, the store never
    guesses."""

    with pytest.raises(ValueError):
        compose_paths(None, {path: None})

    assert compose_paths(None, {canonicalize(path): None}) == {
        "/usr/bin": None
    }


# A mode is a mode, and zero is one of them


@pytest.mark.parametrize(
    "written,applied",
    [
        # An unquoted mode is an integer by the time a task sees it,
        # and an integer is the mode's numeric value, as the builtin
        # file modules read one
        (0, "0000"),
        (420, "0644"),
        (0o755, "0755"),
        # YAML reads a leading zero as octal, so 0644 arrives as 420
        # and is the mode it looks like; 644 is decimal and is not
        (644, "01204"),
        # A quoted mode is left exactly as it was written
        ("0", "0"),
        ("0644", "0644"),
        ("644", "644"),
    ],
)
def test_normalize_mode_renders_a_written_mode_for_chmod(
    written: Any, applied: str
) -> None:
    """Test every mode a task can write arrives as the octal string a
    command takes, and that an integer keeps the numeric value the
    builtin file modules give it."""

    assert normalize_mode(written) == applied


def test_normalize_mode_leaves_an_unset_mode_unset() -> None:
    """Test only an unset mode is unset.  Mode 0 is a mode, so the
    guards downstream ask whether the mode is None."""

    assert normalize_mode(None) is None
    assert normalize_mode(0) is not None


def test_normalize_mode_refuses_an_empty_mode() -> None:
    """Test an empty string is not an unset mode and is not a mode,
    so it is named rather than passed to a command that would fail on
    it obscurely.  The builtin file modules refuse it too."""

    with pytest.raises(ValueError, match="must not be empty"):
        normalize_mode("")


@pytest.mark.parametrize("mode", [-1, -0o755])
def test_normalize_mode_refuses_a_negative_mode(mode: int) -> None:
    """Test a negative mode is refused by name rather than composed
    into a command that would fail obscurely."""

    with pytest.raises(ValueError, match="negative"):
        normalize_mode(mode)


@pytest.mark.parametrize("mode", [["0644"], {"mode": "0644"}, 0.644])
def test_normalize_mode_refuses_what_is_not_a_mode(mode: Any) -> None:
    """Test a mode that is neither a string nor an integer is named
    as such, since raw accepts anything the task wrote."""

    with pytest.raises(ValueError, match="octal string or an integer"):
        normalize_mode(mode)
