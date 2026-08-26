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

"""Composition and lookup of the canonical user and group facts.

``compose_users_groups`` is the one definition of ``o0_users`` and
``o0_groups``: both are keyed by the stringified numeric ID, both
carry that ID as an integer field, and membership is expressed in
integer IDs on both sides.  ``compose_homes`` and
``compose_shell_files`` define the two facts that follow from them,
the directories users live in and the shells they log in with, each
taking the caller's own way of reading a path's metadata.  Every
producer of these facts composes them here so consumers see one
shape.
"""

from __future__ import annotations

from typing import Any, Callable, Optional, Union

from ansible_collections.o0_o.posix.plugins.module_utils.group_utils import (
    group_info,
)
from ansible_collections.o0_o.posix.plugins.module_utils.passwd_utils import (
    passwd_info,
)

Source = Union[str, dict[str, Any], list[dict[str, Any]]]

# How a producer reads metadata for a list of paths: the read action's
# result, carrying one entry per path under its ``paths`` key
ReadPaths = Callable[[list[str]], dict[str, Any]]


def compose_users_groups(
    passwd: Source,
    group: Source,
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    """Compose the canonical o0_users and o0_groups facts.

    Users are keyed by stringified UID and carry ``name``, ``uid``,
    ``gid`` (the primary group), ``gecos``, ``home``, ``shell``, and
    ``groups`` (every GID the user belongs to, primary group
    included).  Groups are keyed by stringified GID and carry
    ``name``, ``gid``, and ``members`` (the UIDs of every member,
    including those who hold the group as their primary).

    :param Source passwd: ``/etc/passwd`` content or a read/slurp
        result holding it
    :param Source group: ``/etc/group`` content or a read/slurp
        result holding it
    :returns tuple[dict[str, dict[str, Any]], dict[str, dict[str,
        Any]]]: The o0_users and o0_groups mappings
    """
    parsed_groups = group_info(group, key="id")

    groups: dict[str, dict[str, Any]] = {
        gid_str: {
            "name": entry.get("name"),
            "gid": int(gid_str),
            "members": [],
        }
        for gid_str, entry in parsed_groups.items()
    }

    users: dict[str, dict[str, Any]] = {}
    uid_by_name: dict[str, int] = {}

    for uid_str, entry in passwd_info(passwd, key="id").items():
        uid = int(uid_str)
        gid = entry.get("gid")
        name = entry.get("name")

        users[uid_str] = {
            "name": name,
            "uid": uid,
            "gid": gid,
            "gecos": entry.get("gecos"),
            "home": entry.get("home"),
            "shell": entry.get("shell"),
            "groups": [] if gid is None else [gid],
        }

        if isinstance(name, str) and name:
            uid_by_name[name] = uid

        if gid is not None:
            _add_member(groups, gid, uid)

    # /etc/group names its members; the canonical fact counts them
    # in UIDs, and a member with no passwd entry has no UID to count.
    for gid_str, entry in parsed_groups.items():
        gid = int(gid_str)
        for member in entry.get("members") or []:
            uid = uid_by_name.get(member)
            if uid is None:
                continue
            user_groups = users[str(uid)]["groups"]
            if gid not in user_groups:
                user_groups.append(gid)
            _add_member(groups, gid, uid)

    return users, groups


def _add_member(groups: dict[str, dict[str, Any]], gid: int, uid: int) -> None:
    """Record a UID as a member of a GID, creating the group entry.

    A primary group that /etc/group never named still exists as far
    as its members are concerned, so it gets an entry with a null
    name rather than being dropped.

    :param dict[str, dict[str, Any]] groups: Group mapping to augment
    :param int gid: Group ID gaining the member
    :param int uid: User ID to record
    """
    entry = groups.setdefault(
        str(gid), {"name": None, "gid": gid, "members": []}
    )
    if uid not in entry["members"]:
        entry["members"].append(uid)


def _read_paths(read: ReadPaths, paths: list[str]) -> dict[str, Any]:
    """Read metadata for paths, answering with what came back.

    :param ReadPaths read: The caller's read
    :param list[str] paths: Paths to inspect
    :returns dict[str, Any]: Metadata per path, empty when the read
        failed
    """
    result = read(paths)
    if result.get("failed") or "paths" not in result:
        return {}
    return {path: data for path, data in result["paths"].items() if data}


def compose_homes(
    users: dict[str, dict[str, Any]],
    read: ReadPaths,
) -> dict[str, dict[str, Any]]:
    """Compose the canonical o0_homes fact.

    Homes are keyed by path and carry the path's own metadata plus
    ``residents``, the UIDs that call it home.  Two users sharing a
    home share an entry.  Where a home is a symlink, the target gets
    an entry of its own carrying the same residents, because that is
    where their files actually are.

    :param dict[str, dict[str, Any]] users: The o0_users mapping
    :param ReadPaths read: How to read a path's metadata
    :returns dict[str, dict[str, Any]]: The o0_homes mapping
    """
    residents_by_home: dict[str, list[int]] = {}
    for user in users.values():
        home = user.get("home")
        uid = user.get("uid")
        if isinstance(home, str) and home and isinstance(uid, int):
            residents_by_home.setdefault(home, []).append(uid)

    if not residents_by_home:
        return {}

    homes: dict[str, dict[str, Any]] = {}
    read_homes = _read_paths(read, list(residents_by_home))

    for home, data in read_homes.items():
        data["tags"] = ["posix", "home"]
        data["residents"] = residents_by_home.get(home, [])
        homes[home] = data

    # A home that is a symlink houses its residents at the target
    for home in list(homes):
        entry = homes[home]
        if entry.get("type") != "link" or "target" not in entry:
            continue

        target = entry["target"]
        residents = residents_by_home.get(home, [])

        if target in homes:
            known = homes[target].setdefault("residents", [])
            homes[target]["residents"] = sorted(set(known) | set(residents))
            continue

        for path, data in _read_paths(read, [target]).items():
            data["tags"] = ["posix", "home"]
            data["residents"] = residents
            homes[path] = data

    return homes


def compose_shell_files(
    users: dict[str, dict[str, Any]],
    read: ReadPaths,
    known: Optional[dict[str, dict[str, Any]]] = None,
) -> dict[str, dict[str, Any]]:
    """Compose the canonical o0_shell_files fact.

    Shell files are keyed by the path of the shell binary and carry
    that path's metadata.  A shell already described in ``known`` is
    kept as it stands rather than read again, so a run adds to what an
    earlier gather published instead of replacing it.

    Distinct from ``o0_shells``, which is the list of paths named in
    /etc/shells: this fact describes the shells users actually hold,
    named or not.

    :param dict[str, dict[str, Any]] users: The o0_users mapping
    :param ReadPaths read: How to read a path's metadata
    :param Optional[dict[str, dict[str, Any]]] known: Shell files a
        previous gather already described
    :returns dict[str, dict[str, Any]]: The o0_shell_files mapping
    """
    shell_files: dict[str, dict[str, Any]] = dict(known or {})

    unread = {
        user["shell"]
        for user in users.values()
        if isinstance(user.get("shell"), str)
        and user["shell"]
        and user["shell"] not in shell_files
    }

    if not unread:
        return shell_files

    for path, data in _read_paths(read, sorted(unread)).items():
        data["tags"] = ["posix", "shell"]
        shell_files[path] = data

    return shell_files


def lookup_user(
    identifier: Union[int, str], users: dict[str, dict[str, Any]]
) -> Optional[dict[str, Any]]:
    """Look up a user in o0_users by UID or username.

    An integer is the fact's own key; a string is matched against
    the ``name`` field of each entry.

    :param Union[int, str] identifier: UID (int) or username (str)
    :param dict[str, dict[str, Any]] users: The o0_users mapping
    :returns Optional[dict[str, Any]]: The user entry, or None if
        not found
    """
    return _lookup(identifier, users)


def lookup_group(
    identifier: Union[int, str], groups: dict[str, dict[str, Any]]
) -> Optional[dict[str, Any]]:
    """Look up a group in o0_groups by GID or group name.

    An integer is the fact's own key; a string is matched against
    the ``name`` field of each entry.

    :param Union[int, str] identifier: GID (int) or group name (str)
    :param dict[str, dict[str, Any]] groups: The o0_groups mapping
    :returns Optional[dict[str, Any]]: The group entry, or None if
        not found
    """
    return _lookup(identifier, groups)


def _lookup(
    identifier: Union[int, str], entries: dict[str, dict[str, Any]]
) -> Optional[dict[str, Any]]:
    """Resolve an ID or a name against a canonical fact mapping.

    :param Union[int, str] identifier: Numeric ID (int) or name (str)
    :param dict[str, dict[str, Any]] entries: The o0_users or
        o0_groups mapping
    :returns Optional[dict[str, Any]]: The matching entry, or None
    """
    if not isinstance(entries, dict):
        return None

    if isinstance(identifier, int) and not isinstance(identifier, bool):
        entry = entries.get(str(identifier))
        return entry if isinstance(entry, dict) else None

    if isinstance(identifier, str):
        for entry in entries.values():
            if isinstance(entry, dict) and entry.get("name") == identifier:
                return entry

    return None


__all__ = [
    "compose_homes",
    "compose_shell_files",
    "compose_users_groups",
    "lookup_group",
    "lookup_user",
]
