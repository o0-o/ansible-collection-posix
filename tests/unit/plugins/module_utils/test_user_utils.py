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

import os

from typing import Any

from ansible_collections.o0_o.posix.plugins.module_utils.group_utils import (
    group_info,
)
from ansible_collections.o0_o.posix.plugins.module_utils.passwd_utils import (
    passwd_info,
)
from ansible_collections.o0_o.posix.plugins.module_utils.path_utils import (
    compose_paths,
)
from ansible_collections.o0_o.posix.plugins.module_utils.user_utils import (
    batch_read,
    compose_homes,
    compose_shell_paths,
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

# A host that resolves its users nowhere but those files, as getent
# would answer it and as the samples above compose without one
SAMPLE_GETENT_PASSWD = SAMPLE_PASSWD
SAMPLE_GETENT_GROUP = SAMPLE_GROUP

FILES = os.path.join(os.path.dirname(__file__), "files")

# The origins the composition names for the samples above, by the kind
# of thing each one is: a path that was read, and the name of a
# command that was consulted.  A kind that contributed nothing is
# empty rather than absent.
FROM_PASSWD: dict[str, list[Any]] = {
    "files": ["/etc/passwd"],
    "commands": [],
}
FROM_PASSWD_AND_GETENT: dict[str, list[Any]] = {
    "files": ["/etc/passwd"],
    "commands": ["getent"],
}
FROM_GETENT_PASSWD: dict[str, list[Any]] = {
    "files": [],
    "commands": ["getent"],
}
FROM_GROUP: dict[str, list[Any]] = {"files": ["/etc/group"], "commands": []}
FROM_GROUP_AND_GETENT: dict[str, list[Any]] = {
    "files": ["/etc/group"],
    "commands": ["getent"],
}
FROM_GETENT_GROUP: dict[str, list[Any]] = {
    "files": [],
    "commands": ["getent"],
}


def _corpus(name: str) -> str:
    """Read a captured enumeration verbatim.

    :param str name: File name under ``files/``
    :returns str: The file's contents
    """
    with open(os.path.join(FILES, name), encoding="utf-8") as handle:
        return handle.read()


# The canonical shape, as composed from the samples above
# The module whose composer made these entries. Every fact this
# collection composes names its producers, and a user entry names the
# users module because user_utils is what composed it; a gather adds
# its own name beside this one.
COMPOSED_BY = "o0_o.posix.users"

USERS = {
    "0": {
        "name": "root",
        "uid": 0,
        "gid": 0,
        "gecos": "System Administrator",
        "home": "/var/root",
        "shell": "/bin/sh",
        "groups": [0],
        "evidence": FROM_PASSWD,
    },
    "1000": {
        "name": "o0-o",
        "uid": 1000,
        "gid": 20,
        "gecos": "o0-o",
        "home": "/home/o0-o",
        "shell": "/bin/zsh",
        "groups": [20, 0, 101],
        "evidence": FROM_PASSWD,
    },
}

GROUPS = {
    "0": {
        "name": "wheel",
        "gid": 0,
        "members": [0, 1000],
        "evidence": FROM_GROUP,
    },
    "20": {
        "name": "staff",
        "gid": 20,
        "members": [1000],
        "evidence": FROM_GROUP,
    },
    "101": {
        "name": "access_bpf",
        "gid": 101,
        "members": [1000],
        "evidence": FROM_GROUP,
    },
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
        "evidence",
        "origins",
    }
    assert set(groups["20"]) == {
        "name",
        "gid",
        "members",
        "evidence",
        "origins",
    }


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
    assert groups["600"] == {
        "name": None,
        "gid": 600,
        "members": [1002],
        "evidence": FROM_PASSWD,
        "origins": [COMPOSED_BY],
    }


def test_compose_users_groups_handles_empty_input() -> None:
    """Test empty content composes empty mappings."""
    assert compose_users_groups("", "") == ({}, {})


def test_a_host_without_getent_composes_what_it_always_did() -> None:
    """Test files-only gathering is unchanged by the overlay existing.

    Passing nothing for the resolved view is the macOS case and the
    case of every host that has no getent, and it has to compose the
    facts the files alone say - saying so in evidence rather than by
    leaving the field off.
    """
    users, groups = compose_users_groups(SAMPLE_PASSWD, SAMPLE_GROUP)
    without = compose_users_groups(SAMPLE_PASSWD, SAMPLE_GROUP, None, None)

    assert users == without[0]
    assert groups == without[1]
    assert users["1000"]["evidence"] == FROM_PASSWD
    assert groups["20"]["evidence"] == FROM_GROUP


def test_a_resolved_view_that_only_repeats_the_files_says_both() -> None:
    """Test agreement is still two origins, not one.

    A files-only host with a real getent gets the same bytes twice.
    Both answered, so both are named: evidence reports what was asked
    and answered, not whether the answers differed.
    """
    users, groups = compose_users_groups(
        SAMPLE_PASSWD,
        SAMPLE_GROUP,
        SAMPLE_GETENT_PASSWD,
        SAMPLE_GETENT_GROUP,
    )

    assert users["1000"]["evidence"] == FROM_PASSWD_AND_GETENT
    assert groups["20"]["evidence"] == FROM_GROUP_AND_GETENT

    # And the facts themselves are what the files alone composed
    files_only = compose_users_groups(SAMPLE_PASSWD, SAMPLE_GROUP)[0]
    assert {
        uid: {k: v for k, v in user.items() if k != "evidence"}
        for uid, user in users.items()
    } == {
        uid: {k: v for k, v in user.items() if k != "evidence"}
        for uid, user in files_only.items()
    }


def test_the_resolved_view_wins_a_field_the_files_disagree_on() -> None:
    """Test getent is the host's own answer about itself."""
    users = compose_users_groups(
        SAMPLE_PASSWD,
        SAMPLE_GROUP,
        SAMPLE_PASSWD.replace("/bin/zsh", "/usr/local/bin/fish"),
        SAMPLE_GROUP,
    )[0]

    assert users["1000"]["shell"] == "/usr/local/bin/fish"
    assert users["1000"]["evidence"] == FROM_PASSWD_AND_GETENT


def test_an_empty_field_the_resolved_view_reported_wins() -> None:
    """Test emptiness is an answer, and the resolved answer wins.

    getent returned the whole entry, so an empty gecos in it is the
    host saying the gecos is empty - not the host declining to say.
    """
    users = compose_users_groups(
        SAMPLE_PASSWD,
        SAMPLE_GROUP,
        "o0-o:*:1000:20::/home/o0-o:/bin/zsh",
        SAMPLE_GROUP,
    )[0]

    assert users["1000"]["gecos"] == ""


def test_a_field_the_resolved_parse_could_not_read_keeps_the_base() -> None:
    """Test a null is the parse failing, which is no answer to prefer.

    A gid the parse could make nothing of comes back null, and a null
    is not a disagreement the resolved view gets to win - the files
    keep what they said rather than losing it.
    """
    users = compose_users_groups(
        SAMPLE_PASSWD,
        SAMPLE_GROUP,
        "o0-o:*:1000::o0-o:/home/o0-o:/bin/zsh",
        SAMPLE_GROUP,
    )[0]

    assert users["1000"]["gid"] == 20


def test_a_user_only_getent_knows_is_added_and_says_so() -> None:
    """Test the overlay covers keys the base never had.

    A directory-resolved user is in no file on the host, so the files
    parse cannot mention them and the resolved view is the whole of
    why they are in the facts at all.
    """
    users, groups = compose_users_groups(
        SAMPLE_PASSWD,
        SAMPLE_GROUP,
        SAMPLE_PASSWD + "\nldap:*:4000:4000:LDAP User:/home/ldap:/bin/sh",
        SAMPLE_GROUP + "\nldapgrp:*:4000:",
    )

    assert users["4000"]["name"] == "ldap"
    assert users["4000"]["evidence"] == FROM_GETENT_PASSWD
    assert groups["4000"]["evidence"] == FROM_GETENT_GROUP


def test_a_group_only_a_resolved_user_implies_borrows_their_evidence() -> None:
    """Test an unnamed primary group's provenance is its claimants'.

    Such a group is in no group source at all - it exists because a
    passwd entry claimed it as a primary - so the only honest thing
    to say about where it came from is where they came from: the
    passwd enumeration that named them, never the group one nobody
    heard it from.
    """
    groups = compose_users_groups(
        SAMPLE_PASSWD,
        SAMPLE_GROUP,
        SAMPLE_PASSWD + "\nldap:*:4000:900:LDAP User:/home/ldap:/bin/sh",
        SAMPLE_GROUP,
    )[1]

    assert groups["900"]["name"] is None
    assert groups["900"]["members"] == [4000]
    assert groups["900"]["evidence"] == FROM_GETENT_PASSWD


def test_membership_does_not_change_a_named_group_s_evidence() -> None:
    """Test a group's evidence is its own record's, not its members'.

    staff is named in the files and nowhere else; that a
    getent-resolved user holds it as a primary says nothing about
    where staff's own record came from.
    """
    groups = compose_users_groups(
        SAMPLE_PASSWD,
        SAMPLE_GROUP,
        SAMPLE_PASSWD + "\nldap:*:4000:20:LDAP User:/home/ldap:/bin/sh",
        None,
    )[1]

    assert 4000 in groups["20"]["members"]
    assert groups["20"]["evidence"] == FROM_GROUP


def test_both_kinds_of_origin_are_always_present() -> None:
    """Test the field holds to the absence discipline everywhere.

    Both a file and a command are attempted for every entry, so a
    kind that contributed nothing to one is gathered and empty rather
    than absent - and no entry is here without an origin naming it.
    """
    users, groups = compose_users_groups(
        SAMPLE_PASSWD,
        SAMPLE_GROUP,
        SAMPLE_PASSWD + "\nldap:*:4000:900:LDAP User:/home/ldap:/bin/sh",
        SAMPLE_GROUP + "\nldapgrp:*:4000:",
    )

    for entry in list(users.values()) + list(groups.values()):
        evidence = entry["evidence"]
        assert set(evidence) == {"files", "commands"}
        assert evidence["files"] + evidence["commands"]
        # A path is a string and a command is the name it is known
        # by, each kind sorted and holding one of each
        for kind in ("files", "commands"):
            assert all(isinstance(name, str) for name in evidence[kind])
            assert evidence[kind] == sorted(set(evidence[kind]))


def test_a_file_names_the_path_it_was_actually_read_from() -> None:
    """Test the origin is the path read, not the path usually read.

    M(o0_o.posix.users) takes the files to read as options, and an
    origin that named /etc/passwd for a file that was never opened
    would be a key joining against the wrong entry of o0_paths.
    """
    users, groups = compose_users_groups(
        SAMPLE_PASSWD,
        SAMPLE_GROUP,
        passwd_path="/etc/master.passwd",
        group_path="/usr/local/etc/group",
    )

    assert users["1000"]["evidence"] == {
        "files": ["/etc/master.passwd"],
        "commands": [],
    }
    assert groups["20"]["evidence"] == {
        "files": ["/usr/local/etc/group"],
        "commands": [],
    }


def test_one_half_of_the_resolved_view_overlays_alone() -> None:
    """Test a getent that answered for one database only is honored.

    Each database is its own probe, so a host whose passwd enumerated
    and whose group did not overlays the half it has rather than
    discarding both.
    """
    users, groups = compose_users_groups(
        SAMPLE_PASSWD, SAMPLE_GROUP, SAMPLE_GETENT_PASSWD, None
    )

    assert users["1000"]["evidence"] == FROM_PASSWD_AND_GETENT
    assert groups["20"]["evidence"] == FROM_GROUP


def test_the_captured_platforms_compose_the_same_shape() -> None:
    """Test every captured enumeration overlays identically.

    Both libcs and both BSDs differ in what they answer about
    themselves - only glibc's getent takes -V - and the BSDs differ
    in format too, dropping the empty members field a Linux group
    line ends with. None of it reaches the fact: one composition
    takes all four, keyed the same and provenanced the same.
    """
    for platform in (
        "linux_glibc",
        "linux_musl",
        "freebsd14",
        "openbsd79",
    ):
        passwd = _corpus(f"getent_passwd_{platform}.txt")
        group = _corpus(f"getent_group_{platform}.txt")
        users, groups = compose_users_groups(passwd, group, passwd, group)

        assert users["0"]["uid"] == 0
        assert users["0"]["evidence"] == FROM_PASSWD_AND_GETENT
        assert groups["0"]["evidence"] == FROM_GROUP_AND_GETENT
        assert all(user["uid"] == int(uid) for uid, user in users.items())
        assert all(group["gid"] == int(gid) for gid, group in groups.items())
        # A group nobody is a secondary member of is a group with no
        # members, however the platform spelled the line
        assert all(
            isinstance(group["members"], list) for group in groups.values()
        )


def test_a_bsd_group_line_with_no_members_still_composes() -> None:
    """Test the shape the BSD captures turned up composes.

    ``bin:*:7`` is what both BSDs' getent prints for a group nobody
    is a secondary member of, and the group is real - it just has
    nobody in it.
    """
    users, groups = compose_users_groups(
        "root:*:0:0:Charlie &:/root:/bin/ksh",
        "wheel:*:0:root",
        "root:*:0:0:Charlie &:/root:/bin/ksh",
        "wheel:*:0:root\nbin:*:7",
    )

    assert groups["7"] == {
        "name": "bin",
        "gid": 7,
        "members": [],
        "origins": [COMPOSED_BY],
        "evidence": FROM_GETENT_GROUP,
    }
    assert users["0"]["evidence"] == FROM_PASSWD_AND_GETENT


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
        return {"paths": {path: answers.get(path) for path in paths}}

    return read, asked


def test_compose_homes_describes_the_home_and_nothing_else() -> None:
    """Test a home entry is what the read said and nothing added.

    Who lives at a home is the join between the users and the store,
    not a field either of them stores, and what a path is to this
    collection is not a fact about the path at all.
    """
    read, asked = _reader(
        {
            "/var/root": {"type": "directory"},
            "/home/o0-o": {"type": "directory"},
            "/home/nogroup": {"type": "directory"},
        }
    )

    homes = compose_homes(USERS, read)

    assert homes["/var/root"] == {"type": "directory"}
    assert homes["/home/o0-o"] == {"type": "directory"}
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
    assert homes["/shared"] == {"type": "directory"}


def test_compose_homes_follows_a_linked_home() -> None:
    """Test a home that is a symlink gets the target an entry too,
    because that is where the user's files are."""
    users = {"1000": {"uid": 1000, "home": "/home/o0-o"}}
    read, _asked = _reader(
        {
            "/home/o0-o": {"type": "link", "target": "/Users/o0-o"},
            "/Users/o0-o": {"type": "directory"},
        }
    )

    homes = compose_homes(users, read)

    assert set(homes) == {"/home/o0-o", "/Users/o0-o"}
    assert homes["/Users/o0-o"] == {"type": "directory"}


def test_compose_homes_files_every_step_of_a_chain() -> None:
    """Test a read that walked the chain puts every step in the store,
    not only the one the link's own text names."""
    users = {"1000": {"uid": 1000, "home": "/home/o0-o"}}
    read, asked = _reader(
        {
            "/home/o0-o": {
                "type": "link",
                "target": "o0-o",
                "resolution": [
                    "/home/o0-o",
                    "/Users/o0-o",
                    "/Volumes/data/o0-o",
                ],
            },
            "/Users/o0-o": {"type": "link", "target": "o0-o"},
            "/Volumes/data/o0-o": {"type": "directory"},
        }
    )

    homes = compose_homes(users, read)

    assert set(homes) == {
        "/home/o0-o",
        "/Users/o0-o",
        "/Volumes/data/o0-o",
    }
    assert homes["/Volumes/data/o0-o"] == {"type": "directory"}
    # The homes first, then every step of every chain, in one batch
    assert asked == [
        ["/home/o0-o"],
        ["/Users/o0-o", "/Volumes/data/o0-o"],
    ]


def test_compose_homes_link_to_a_known_home() -> None:
    """Test a link whose target is another user's home leaves that
    target's own entry as it stands rather than reading it again."""
    users = {
        "0": {"uid": 0, "home": "/shared"},
        "1000": {"uid": 1000, "home": "/link"},
    }
    read, asked = _reader(
        {
            "/shared": {"type": "directory"},
            "/link": {"type": "link", "target": "/shared"},
        }
    )

    homes = compose_homes(users, read)

    assert homes["/shared"] == {"type": "directory"}
    assert asked == [["/link", "/shared"]]


def test_compose_homes_without_homes() -> None:
    """Test users with no home directory read no paths at all."""
    read, asked = _reader({})

    assert compose_homes({"0": {"uid": 0}}, read) == {}
    assert asked == []


def test_compose_homes_keys_a_home_the_way_the_store_does() -> None:
    """Test a home is filed under what it is rather than under how
    /etc/passwd wrote it, since the entry is a key of the path
    store."""
    users = {"1000": {"uid": 1000, "home": "/home/o0-o/"}}
    read, _asked = _reader({"/home/o0-o/": {"type": "directory"}})

    homes = compose_homes(users, read)

    assert list(homes) == ["/home/o0-o"]
    assert homes["/home/o0-o"] == {"type": "directory"}


def test_compose_homes_two_spellings_are_one_home() -> None:
    """Test two users who wrote one home two ways live in one entry,
    because the store keys the path once."""
    users = {
        "0": {"uid": 0, "home": "/shared"},
        "1": {"uid": 1, "home": "/shared/"},
    }
    read, _asked = _reader(
        {
            "/shared": {"type": "directory"},
            "/shared/": {"type": "directory"},
        }
    )

    homes = compose_homes(users, read)

    assert list(homes) == ["/shared"]
    assert homes["/shared"] == {"type": "directory"}


def test_compose_homes_drops_a_home_the_store_cannot_key() -> None:
    """Test a passwd field that names no path is left out rather than
    filed under a key the store would refuse."""
    users = {"1000": {"uid": 1000, "home": "nonexistent"}}
    read, _asked = _reader({"nonexistent": {"type": "directory"}})

    assert compose_homes(users, read) == {}


def test_compose_homes_resolves_a_relative_link_target() -> None:
    """Test a relative symlink target is resolved against the
    directory the link lives in, the way the kernel resolves it, so
    the target keys the store as the path it is."""
    users = {"1000": {"uid": 1000, "home": "/home/o0-o"}}
    read, _asked = _reader(
        {
            "/home/o0-o": {"type": "link", "target": "../Users/o0-o"},
            "/Users/o0-o": {"type": "directory"},
        }
    )

    homes = compose_homes(users, read)

    assert set(homes) == {"/home/o0-o", "/Users/o0-o"}
    assert homes["/Users/o0-o"] == {"type": "directory"}


def test_compose_homes_relative_link_to_a_known_home() -> None:
    """Test a relative target that resolves onto another home is that
    home rather than a second entry for the same path."""
    users = {
        "0": {"uid": 0, "home": "/home/shared"},
        "1000": {"uid": 1000, "home": "/home/o0-o"},
    }
    read, _asked = _reader(
        {
            "/home/shared": {"type": "directory"},
            "/home/o0-o": {"type": "link", "target": "shared"},
        }
    )

    homes = compose_homes(users, read)

    assert set(homes) == {"/home/shared", "/home/o0-o"}
    assert homes["/home/shared"] == {"type": "directory"}


def test_compose_homes_drops_a_target_that_keys_nothing() -> None:
    """Test a link whose target the store cannot key leaves the link
    itself intact and adds nothing beside it."""
    users = {"1000": {"uid": 1000, "home": "/home/o0-o"}}
    read, _asked = _reader({"/home/o0-o": {"type": "link", "target": ""}})

    homes = compose_homes(users, read)

    assert list(homes) == ["/home/o0-o"]


def test_compose_homes_answers_in_the_shape_the_store_takes() -> None:
    """Test the composition is an observation compose_paths accepts as
    it stands, which is what makes a home an entry of the path store
    rather than a namespace of its own."""
    users = {"1000": {"uid": 1000, "home": "/home/o0-o"}}
    read, _asked = _reader({"/home/o0-o": {"type": "directory"}})

    homes = compose_homes(users, read)

    assert compose_paths(None, homes) == homes


def test_compose_homes_files_a_home_that_is_not_there_as_a_null() -> None:
    """Test a home the read confirmed is not there is filed null, so a
    user whose home was never made keeps saying so."""
    users = {"1000": {"uid": 1000, "home": "/home/ghost"}}
    read, _asked = _reader({})

    homes = compose_homes(users, read)

    assert homes == {"/home/ghost": None}
    assert compose_paths(None, homes) == homes


def test_compose_homes_leaves_out_a_home_no_read_reached() -> None:
    """Test a read that failed teaches nothing, so the homes it would
    have described are left out rather than called absent."""
    users = {"1000": {"uid": 1000, "home": "/home/o0-o"}}

    def read(paths: list[str]) -> dict[str, Any]:
        return {"failed": True, "msg": "no"}

    assert compose_homes(users, read) == {}


def test_compose_homes_null_never_covers_a_home_that_is_there() -> None:
    """Test one spelling read as absent does not bury the entry the
    other spelling described, since both name one path."""
    users = {
        "0": {"uid": 0, "home": "/shared/"},
        "1": {"uid": 1, "home": "/shared"},
    }
    read, _asked = _reader({"/shared": {"type": "directory"}})

    homes = compose_homes(users, read)

    assert homes["/shared"] == {"type": "directory"}


def test_compose_homes_files_a_dangling_link_target_as_a_null() -> None:
    """Test a home that links somewhere nothing is files the target as
    a null, because that is where the residents' files are not."""
    users = {"1000": {"uid": 1000, "home": "/home/o0-o"}}
    read, _asked = _reader(
        {"/home/o0-o": {"type": "link", "target": "/Users/o0-o"}}
    )

    homes = compose_homes(users, read)

    assert homes["/Users/o0-o"] is None
    assert homes["/home/o0-o"]["type"] == "link"


def test_compose_shell_paths_describes_held_shells() -> None:
    """Test the shells users hold are entries of the path store."""
    read, asked = _reader(
        {
            "/bin/sh": {"type": "regular"},
            "/bin/zsh": {"type": "regular"},
        }
    )

    shells = compose_shell_paths(USERS, read)

    assert set(shells) == {"/bin/sh", "/bin/zsh"}
    assert shells["/bin/sh"] == {"type": "regular"}
    assert len(asked) == 1


def test_compose_shell_paths_files_every_hop_of_a_chain() -> None:
    """Test a shell that is a link puts what it resolves to in the
    store beside it, which is what the question about /bin/sh is."""
    read, asked = _reader(
        {
            "/bin/sh": {
                "type": "link",
                "target": "bash",
                "resolution": ["/bin/sh", "/usr/bin/sh", "/usr/bin/bash"],
            },
            "/bin/zsh": {"type": "regular"},
            "/usr/bin/sh": {"type": "link", "target": "bash"},
            "/usr/bin/bash": {"type": "regular"},
        }
    )

    shells = compose_shell_paths(USERS, read)

    assert set(shells) == {
        "/bin/sh",
        "/bin/zsh",
        "/usr/bin/sh",
        "/usr/bin/bash",
    }
    assert shells["/usr/bin/bash"] == {"type": "regular"}
    # The shells first, then every step of every chain, in one batch
    assert asked == [
        ["/bin/sh", "/bin/zsh"],
        ["/usr/bin/bash", "/usr/bin/sh"],
    ]


def test_compose_shell_paths_reads_no_hop_twice() -> None:
    """Test a step the store or the batch already describes is not
    read again."""
    read, asked = _reader(
        {
            "/bin/sh": {
                "type": "link",
                "resolution": ["/bin/sh", "/usr/bin/bash"],
            },
            "/bin/zsh": {
                "type": "link",
                "resolution": ["/bin/zsh", "/usr/bin/bash"],
            },
            "/usr/bin/bash": {"type": "regular"},
        }
    )

    compose_shell_paths(USERS, read)

    assert asked[1] == ["/usr/bin/bash"]
    assert len(asked) == 2


def test_compose_shell_paths_keeps_what_the_store_describes() -> None:
    """Test a shell the store already describes is left alone and is
    not read again."""
    read, asked = _reader({"/bin/zsh": {"type": "regular"}})

    shells = compose_shell_paths(
        USERS, read, {"/bin/sh": {"type": "regular", "known": True}}
    )

    assert set(shells) == {"/bin/zsh"}
    assert asked == [["/bin/zsh"]]


def test_compose_shell_paths_reads_nothing_new() -> None:
    """Test a run with every shell already described reads no paths."""
    read, asked = _reader({})

    shells = compose_shell_paths(
        USERS,
        read,
        {"/bin/sh": {"type": "regular"}, "/bin/zsh": {"type": "regular"}},
    )

    assert shells == {}
    assert asked == []


def test_a_key_without_a_type_is_not_a_description() -> None:
    """Test a null the command sweep filed, and an entry carrying
    only an executable row, are not a shell the store has read."""
    read, asked = _reader(
        {"/bin/sh": {"type": "regular"}, "/bin/zsh": {"type": "regular"}}
    )

    shells = compose_shell_paths(
        USERS,
        read,
        {"/bin/sh": None, "/bin/zsh": {"executable": {"0": True}}},
    )

    assert set(shells) == {"/bin/sh", "/bin/zsh"}
    assert asked == [["/bin/sh", "/bin/zsh"]]


def test_composition_is_what_renames_the_util_shapes() -> None:
    """Test the passwd and group utils keep their own field names and
    this composition is what turns them into a fact.

    Those utils are the /etc/passwd and /etc/group filters' parsers,
    and their shapes are those filters' published API. The rule is
    that a producer of an o0_ fact routes through here rather than
    publishing a util's shape under a fact's name.
    """
    raw_users = passwd_info(SAMPLE_PASSWD, key="id")
    raw_groups = group_info(SAMPLE_GROUP, key="id")

    # What the utils answer with, left alone
    assert "uid" not in raw_users["1000"]
    assert "gid" not in raw_groups["101"]
    assert raw_groups["101"]["members"] == ["o0-o", "ghost"]

    users, groups = compose_users_groups(SAMPLE_PASSWD, SAMPLE_GROUP)

    # What a fact carries: the numeric ID as a field, membership in
    # numeric IDs, and a member with no passwd entry left out
    assert users["1000"]["uid"] == 1000
    assert groups["101"]["gid"] == 101
    assert groups["101"]["members"] == [1000]


# The metadata a batched gather stands to read: two homes, one of
# them a link, and the two shells those users hold
BATCH_ANSWERS = {
    "/var/root": {"type": "directory"},
    "/home/o0-o": {"type": "link", "target": "/Users/o0-o"},
    "/Users/o0-o": {"type": "directory"},
    "/bin/sh": {"type": "regular"},
    "/bin/zsh": {"type": "regular"},
}


def test_batch_read_reads_homes_and_shells_together() -> None:
    """Test both compositions are served by one read over the union
    of the paths they need, deduplicated and in a settled order."""
    read, asked = _reader(BATCH_ANSWERS)

    batched = batch_read(USERS, read)
    compose_homes(USERS, batched)
    compose_shell_paths(USERS, batched)

    # The batch, then only the linked home's target
    assert asked[0] == ["/bin/sh", "/bin/zsh", "/home/o0-o", "/var/root"]
    assert asked[1] == ["/Users/o0-o"]
    assert len(asked) == 2


def test_batch_read_composes_what_an_unbatched_read_composes() -> None:
    """Test the facts are identical to the ones the compositions
    reach when each does its own read."""
    plain, plain_asked = _reader(BATCH_ANSWERS)
    plain_homes = compose_homes(USERS, plain)
    plain_shells = compose_shell_paths(USERS, plain)

    read, asked = _reader(BATCH_ANSWERS)
    batched = batch_read(USERS, read)
    homes = compose_homes(USERS, batched)
    shells = compose_shell_paths(USERS, batched)

    assert homes == plain_homes
    assert shells == plain_shells
    # Same facts, fewer reads
    assert len(asked) < len(plain_asked)


def test_batch_read_keeps_the_merge_of_a_linked_home() -> None:
    """Test a link whose target is another user's home still merges
    into that target rather than reading it again."""
    users = {
        "0": {"uid": 0, "home": "/shared", "shell": "/bin/sh"},
        "1000": {"uid": 1000, "home": "/link", "shell": "/bin/sh"},
    }
    read, asked = _reader(
        {
            "/shared": {"type": "directory"},
            "/link": {"type": "link", "target": "/shared"},
            "/bin/sh": {"type": "regular"},
        }
    )

    homes = compose_homes(users, batch_read(users, read))

    assert homes["/shared"] == {"type": "directory"}
    assert asked == [["/bin/sh", "/link", "/shared"]]


def test_batch_read_leaves_known_shells_out_of_the_batch() -> None:
    """Test a shell a previous gather described is not read, the same
    way the composition would not have read it."""
    known = {"/bin/sh": {"type": "regular", "known": True}}
    read, asked = _reader(BATCH_ANSWERS)

    batched = batch_read(USERS, read, known)
    shells = compose_shell_paths(USERS, batched, known)

    assert "/bin/sh" not in asked[0]
    assert set(shells) == {"/bin/zsh"}
    assert shells["/bin/zsh"] == {"type": "regular"}


def test_batch_read_reads_nothing_without_paths() -> None:
    """Test users with neither a home nor a shell cost no read at
    all, batch included."""
    read, asked = _reader({})

    batched = batch_read({"0": {"uid": 0}}, read)

    assert compose_homes({"0": {"uid": 0}}, batched) == {}
    assert compose_shell_paths({"0": {"uid": 0}}, batched) == {}
    assert asked == []


def test_batch_read_falls_through_when_the_batch_fails() -> None:
    """Test a failed batch changes nothing: each composition reads
    for itself, as it always did."""
    asked: list[list[str]] = []

    def read(paths: list[str]) -> dict[str, Any]:
        asked.append(list(paths))
        if len(asked) == 1:
            return {"failed": True, "msg": "no"}
        return {"paths": {path: BATCH_ANSWERS.get(path) for path in paths}}

    batched = batch_read(USERS, read)
    homes = compose_homes(USERS, batched)
    shells = compose_shell_paths(USERS, batched)

    assert asked[1] == ["/home/o0-o", "/var/root"]
    assert sorted(homes) == ["/Users/o0-o", "/home/o0-o", "/var/root"]
    assert set(shells) == {"/bin/sh", "/bin/zsh"}


def test_batch_read_answers_each_composition_its_own_copy() -> None:
    """Test one path serving as both a home and a shell gets an entry
    each rather than one mapping the two compositions share, so that
    what either of them writes cannot reach the other."""
    users = {"0": {"uid": 0, "home": "/opt/box", "shell": "/opt/box"}}
    answers = {"/opt/box": {"type": "directory"}}

    def read(paths: list[str]) -> dict[str, Any]:
        return {"paths": {path: dict(answers[path]) for path in paths}}

    batched = batch_read(users, read)
    homes = compose_homes(users, batched)
    shells = compose_shell_paths(users, batched)

    assert homes["/opt/box"] == {"type": "directory"}
    assert shells["/opt/box"] == {"type": "directory"}
    assert homes["/opt/box"] is not shells["/opt/box"]


# A modern Linux: /etc/shells names /bin/sh and /bin/rbash and no
# passwd entry holds either of them, while /bin itself is a link to
# usr/bin and both named shells are links to bash. The store has to
# describe all of them, which is what the owner asks of /bin/sh.
NAMED_ONLY = ["/bin/sh", "/bin/rbash", "/bin/bash", "/bin/zsh"]
HOLDERS = {
    "0": {"uid": 0, "home": "/root", "shell": "/bin/bash"},
    "1000": {"uid": 1000, "home": "/home/o0-o", "shell": "/bin/zsh"},
}
CASA_ANSWERS = {
    "/root": {"type": "directory"},
    "/home/o0-o": {"type": "directory"},
    "/bin/bash": {
        "type": "regular",
        "resolution": ["/bin/bash", "/usr/bin/bash"],
    },
    "/bin/zsh": {
        "type": "regular",
        "resolution": ["/bin/zsh", "/usr/bin/zsh"],
    },
    "/bin/sh": {
        "type": "link",
        "target": "bash",
        "resolution": ["/bin/sh", "/usr/bin/sh", "/usr/bin/bash"],
    },
    "/bin/rbash": {
        "type": "link",
        "target": "bash",
        "resolution": ["/bin/rbash", "/usr/bin/rbash", "/usr/bin/bash"],
    },
    "/usr/bin/sh": {"type": "link", "target": "bash"},
    "/usr/bin/rbash": {"type": "link", "target": "bash"},
    "/usr/bin/bash": {"type": "regular"},
    "/usr/bin/zsh": {"type": "regular"},
}


def test_compose_shell_paths_reads_a_shell_nobody_holds() -> None:
    """Test a login shell the host names is described anyway.

    No passwd entry on a modern Linux says /bin/sh, and /bin/sh is
    still what the host means by the name, so reading only what users
    hold leaves out the one shell a consumer is most likely to be
    asking about.
    """
    read, _asked = _reader(CASA_ANSWERS)

    shells = compose_shell_paths(HOLDERS, read, None, NAMED_ONLY)

    assert shells["/bin/sh"]["type"] == "link"
    assert shells["/bin/sh"]["target"] == "bash"
    assert shells["/bin/rbash"]["type"] == "link"


def test_compose_shell_paths_keeps_two_links_that_share_a_target() -> None:
    """Test each spelled shell keeps its own entry and its own chain.

    Two links resolving to one file are two paths, and the store keys
    a path by what it is: the shared target gets an entry of its own
    rather than standing in for either link.
    """
    read, _asked = _reader(CASA_ANSWERS)

    shells = compose_shell_paths(HOLDERS, read, None, NAMED_ONLY)

    assert shells["/bin/sh"]["resolution"] == [
        "/bin/sh",
        "/usr/bin/sh",
        "/usr/bin/bash",
    ]
    assert shells["/bin/rbash"]["resolution"] == [
        "/bin/rbash",
        "/usr/bin/rbash",
        "/usr/bin/bash",
    ]
    assert shells["/usr/bin/bash"] == {"type": "regular"}


def test_compose_shell_paths_files_every_spelled_shell_and_hop() -> None:
    """Test the whole store the casa layout composes to."""
    read, asked = _reader(CASA_ANSWERS)

    shells = compose_shell_paths(HOLDERS, read, None, NAMED_ONLY)

    assert set(shells) == {
        "/bin/bash",
        "/bin/rbash",
        "/bin/sh",
        "/bin/zsh",
        "/usr/bin/bash",
        "/usr/bin/rbash",
        "/usr/bin/sh",
        "/usr/bin/zsh",
    }
    # The shells first, then every step of every chain, in one batch
    assert asked == [
        ["/bin/bash", "/bin/rbash", "/bin/sh", "/bin/zsh"],
        [
            "/usr/bin/bash",
            "/usr/bin/rbash",
            "/usr/bin/sh",
            "/usr/bin/zsh",
        ],
    ]


def test_compose_shell_paths_takes_the_union_of_both_reasons() -> None:
    """Test a shell a user holds is read whether the file names it.

    The file says what the host is willing to call a login shell and
    the passwd entry says what somebody logs in with; either is reason
    enough, and neither is the whole list.
    """
    users = {"0": {"uid": 0, "shell": "/bin/held"}}
    read, asked = _reader(
        {"/bin/held": {"type": "regular"}, "/bin/named": {"type": "regular"}}
    )

    shells = compose_shell_paths(users, read, None, ["/bin/named"])

    assert set(shells) == {"/bin/held", "/bin/named"}
    assert asked[0] == ["/bin/held", "/bin/named"]


def test_compose_shell_paths_reads_no_named_shell_twice() -> None:
    """Test a shell both held and named is one path in the batch."""
    users = {"0": {"uid": 0, "shell": "/bin/sh"}}
    read, asked = _reader({"/bin/sh": {"type": "regular"}})

    compose_shell_paths(users, read, None, ["/bin/sh"])

    assert asked == [["/bin/sh"]]


def test_batch_read_covers_the_shells_the_file_names() -> None:
    """Test the named shells ride the one batch the compositions share.

    A named shell the batch left out would fall through to a read of
    its own, which is the round trip the batch exists to avoid.
    """
    read, asked = _reader(CASA_ANSWERS)

    batched = batch_read(HOLDERS, read, None, NAMED_ONLY)
    compose_homes(HOLDERS, batched)
    compose_shell_paths(HOLDERS, batched, None, NAMED_ONLY)

    assert asked[0] == [
        "/bin/bash",
        "/bin/rbash",
        "/bin/sh",
        "/bin/zsh",
        "/home/o0-o",
        "/root",
    ]
