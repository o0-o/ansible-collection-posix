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

"""Unit tests for user_utils module."""

from __future__ import annotations

from typing import Any

from ansible_collections.o0_o.posix.plugins.module_utils.user_utils import (
    compose_homes,
    compose_shell_files,
    compose_users_groups,
    lookup_group,
    lookup_user,
)

SAMPLE_PASSWD = "\n".join(
    [
        "root:*:0:0:System Administrator:/var/root:/bin/sh",
        "o0-o:*:1000:20:o0-o:/home/o0-o:/bin/zsh",
        "nogroup:*:1001::nogroup:/home/nogroup:/bin/sh",
    ]
)

SAMPLE_GROUP = "\n".join(
    [
        "wheel:*:0:root,o0-o",
        "staff:*:20:",
        "access_bpf:*:101:o0-o,ghost",
    ]
)

# The canonical shape, as composed from the samples above
USERS = {
    "0": {
        "name": "root",
        "uid": 0,
        "gid": 0,
        "gecos": "System Administrator",
        "home": "/var/root",
        "shell": "/bin/sh",
        "groups": [0],
    },
    "1000": {
        "name": "o0-o",
        "uid": 1000,
        "gid": 20,
        "gecos": "o0-o",
        "home": "/home/o0-o",
        "shell": "/bin/zsh",
        "groups": [20, 0, 101],
    },
}

GROUPS = {
    "0": {"name": "wheel", "gid": 0, "members": [0, 1000]},
    "20": {"name": "staff", "gid": 20, "members": [1000]},
    "101": {"name": "access_bpf", "gid": 101, "members": [1000]},
}


def test_compose_users_groups_field_census() -> None:
    """Test the canonical user and group entries carry exactly the
    documented fields."""
    users, groups = compose_users_groups(SAMPLE_PASSWD, SAMPLE_GROUP)

    assert set(users["1000"]) == {
        "name",
        "uid",
        "gid",
        "gecos",
        "home",
        "shell",
        "groups",
    }
    assert set(groups["20"]) == {"name", "gid", "members"}


def test_compose_users_groups_keys_by_uid_and_gid() -> None:
    """Test both mappings key on the stringified numeric ID."""
    users, groups = compose_users_groups(SAMPLE_PASSWD, SAMPLE_GROUP)

    assert users["1000"]["name"] == "o0-o"
    assert users["1000"]["uid"] == 1000
    assert groups["20"]["name"] == "staff"
    assert groups["20"]["gid"] == 20


def test_compose_users_groups_keeps_primary_gid() -> None:
    """Test the primary group survives as an integer gid field."""
    users = compose_users_groups(SAMPLE_PASSWD, SAMPLE_GROUP)[0]

    assert users["0"]["gid"] == 0
    assert users["1000"]["gid"] == 20
    assert "group" not in users["1000"]


def test_compose_users_groups_membership_is_numeric() -> None:
    """Test membership is expressed in integer IDs on both sides."""
    users, groups = compose_users_groups(SAMPLE_PASSWD, SAMPLE_GROUP)

    assert sorted(users["1000"]["groups"]) == [0, 20, 101]
    assert sorted(groups["0"]["members"]) == [0, 1000]
    assert sorted(groups["101"]["members"]) == [1000]


def test_compose_users_groups_counts_primary_membership() -> None:
    """Test a user counts as a member of their primary group even
    when /etc/group does not name them."""
    groups = compose_users_groups(SAMPLE_PASSWD, SAMPLE_GROUP)[1]

    assert groups["20"]["members"] == [1000]


def test_compose_users_groups_skips_unknown_members() -> None:
    """Test a group member with no passwd entry has no UID to count."""
    users, groups = compose_users_groups(SAMPLE_PASSWD, SAMPLE_GROUP)

    assert "ghost" not in {user["name"] for user in users.values()}
    assert groups["101"]["members"] == [1000]


def test_compose_users_groups_user_without_primary_group() -> None:
    """Test a passwd entry with no gid carries a null gid and no
    group memberships."""
    users = compose_users_groups(SAMPLE_PASSWD, SAMPLE_GROUP)[0]

    assert users["1001"]["gid"] is None
    assert users["1001"]["groups"] == []


def test_compose_users_groups_invents_unnamed_primary_group() -> None:
    """Test a primary group absent from /etc/group still gets an
    entry, named null."""
    users, groups = compose_users_groups(
        "svc:*:1002:600::/var/empty:/sbin/nologin", ""
    )

    assert users["1002"]["gid"] == 600
    assert groups["600"] == {"name": None, "gid": 600, "members": [1002]}


def test_compose_users_groups_handles_empty_input() -> None:
    """Test empty content composes empty mappings."""
    assert compose_users_groups("", "") == ({}, {})


def test_lookup_user_by_uid() -> None:
    """Test looking up a user by UID hits the fact's own key."""
    assert lookup_user(1000, USERS) == USERS["1000"]


def test_lookup_user_by_name() -> None:
    """Test looking up a user by name scans the name fields."""
    assert lookup_user("o0-o", USERS) == USERS["1000"]


def test_lookup_user_not_found() -> None:
    """Test a UID and a name that match nothing return None."""
    assert lookup_user(9999, USERS) is None
    assert lookup_user("nobody", USERS) is None


def test_lookup_user_numeric_string_is_a_name() -> None:
    """Test a string is only ever matched against names, so it does
    not resolve as a key."""
    assert lookup_user("1000", USERS) is None


def test_lookup_user_with_none_users() -> None:
    """Test a missing mapping returns None."""
    assert lookup_user(1000, None) is None


def test_lookup_user_with_invalid_type() -> None:
    """Test an identifier that is neither int nor str returns None."""
    assert lookup_user([], USERS) is None


def test_lookup_group_by_gid() -> None:
    """Test looking up a group by GID hits the fact's own key."""
    assert lookup_group(20, GROUPS) == GROUPS["20"]


def test_lookup_group_by_name() -> None:
    """Test looking up a group by name scans the name fields."""
    assert lookup_group("staff", GROUPS) == GROUPS["20"]


def test_lookup_group_not_found() -> None:
    """Test a GID and a name that match nothing return None."""
    assert lookup_group(9999, GROUPS) is None
    assert lookup_group("nogroup", GROUPS) is None


def test_lookup_group_with_none_groups() -> None:
    """Test a missing mapping returns None."""
    assert lookup_group(20, None) is None


def test_lookup_group_with_invalid_type() -> None:
    """Test an identifier that is neither int nor str returns None."""
    assert lookup_group([], GROUPS) is None


def test_lookups_read_composed_facts() -> None:
    """Test the lookups resolve against what the composition emits."""
    users, groups = compose_users_groups(SAMPLE_PASSWD, SAMPLE_GROUP)

    assert lookup_user(0, users)["name"] == "root"
    assert lookup_user("o0-o", users)["uid"] == 1000
    assert lookup_group(101, groups)["name"] == "access_bpf"
    assert lookup_group("wheel", groups)["gid"] == 0


def _reader(
    answers: dict[str, dict[str, Any]],
) -> tuple[Any, list[list[str]]]:
    """Build a read that answers from a path-to-metadata mapping.

    :param dict[str, dict[str, Any]] answers: Metadata per path
    :returns tuple[Any, list[list[str]]]: The read and the list of
        path lists it was asked for
    """
    asked: list[list[str]] = []

    def read(paths: list[str]) -> dict[str, Any]:
        asked.append(list(paths))
        return {
            "paths": {
                path: answers.get(path) for path in paths
            }
        }

    return read, asked


def test_compose_homes_records_residents_as_uids() -> None:
    """Test each home carries the UIDs that call it home."""
    read, asked = _reader(
        {
            "/var/root": {"type": "directory"},
            "/home/o0-o": {"type": "directory"},
            "/home/nogroup": {"type": "directory"},
        }
    )

    homes = compose_homes(USERS, read)

    assert homes["/var/root"]["residents"] == [0]
    assert homes["/home/o0-o"]["residents"] == [1000]
    assert homes["/var/root"]["tags"] == ["posix", "home"]
    # One round trip for every home
    assert len(asked) == 1
    assert sorted(asked[0]) == ["/home/o0-o", "/var/root"]


def test_compose_homes_shares_one_entry() -> None:
    """Test two users sharing a home share its entry."""
    users = {
        "0": {"uid": 0, "home": "/shared", "shell": "/bin/sh"},
        "1": {"uid": 1, "home": "/shared", "shell": "/bin/sh"},
    }
    read, _asked = _reader({"/shared": {"type": "directory"}})

    homes = compose_homes(users, read)

    assert list(homes) == ["/shared"]
    assert homes["/shared"]["residents"] == [0, 1]


def test_compose_homes_follows_a_linked_home() -> None:
    """Test a home that is a symlink houses its residents at the
    target, which is where their files are."""
    users = {"1000": {"uid": 1000, "home": "/home/o0-o"}}
    read, _asked = _reader(
        {
            "/home/o0-o": {"type": "link", "target": "/Users/o0-o"},
            "/Users/o0-o": {"type": "directory"},
        }
    )

    homes = compose_homes(users, read)

    assert set(homes) == {"/home/o0-o", "/Users/o0-o"}
    assert homes["/Users/o0-o"]["residents"] == [1000]
    assert homes["/Users/o0-o"]["tags"] == ["posix", "home"]


def test_compose_homes_link_to_a_known_home() -> None:
    """Test a link whose target is another user's home adds to that
    target's residents rather than replacing them."""
    users = {
        "0": {"uid": 0, "home": "/shared"},
        "1000": {"uid": 1000, "home": "/link"},
    }
    read, _asked = _reader(
        {
            "/shared": {"type": "directory"},
            "/link": {"type": "link", "target": "/shared"},
        }
    )

    homes = compose_homes(users, read)

    assert homes["/shared"]["residents"] == [0, 1000]


def test_compose_homes_without_homes() -> None:
    """Test users with no home directory read no paths at all."""
    read, asked = _reader({})

    assert compose_homes({"0": {"uid": 0}}, read) == {}
    assert asked == []


def test_compose_shell_files_describes_held_shells() -> None:
    """Test the shells users hold are described, keyed by path."""
    read, asked = _reader(
        {
            "/bin/sh": {"type": "regular"},
            "/bin/zsh": {"type": "regular"},
        }
    )

    shell_files = compose_shell_files(USERS, read)

    assert set(shell_files) == {"/bin/sh", "/bin/zsh"}
    assert shell_files["/bin/sh"]["tags"] == ["posix", "shell"]
    assert len(asked) == 1


def test_compose_shell_files_keeps_what_is_known() -> None:
    """Test a shell a previous gather described is kept as it stands
    and is not read again."""
    read, asked = _reader({"/bin/zsh": {"type": "regular"}})

    shell_files = compose_shell_files(
        USERS, read, {"/bin/sh": {"type": "regular", "known": True}}
    )

    assert shell_files["/bin/sh"]["known"] is True
    assert asked == [["/bin/zsh"]]


def test_compose_shell_files_reads_nothing_new() -> None:
    """Test a run with every shell already known reads no paths."""
    read, asked = _reader({})

    shell_files = compose_shell_files(
        USERS,
        read,
        {"/bin/sh": {"type": "regular"}, "/bin/zsh": {"type": "regular"}},
    )

    assert set(shell_files) == {"/bin/sh", "/bin/zsh"}
    assert asked == []
