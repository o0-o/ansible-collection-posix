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
``compose_shell_files`` define what follows from them, the
directories users live in and the shells they log in with, each
taking the caller's own way of reading a path's metadata.  Homes are
paths, so they are entries of the ``o0_paths`` store rather than a
namespace of their own, and ``compose_homes`` answers in the shape
``compose_paths`` takes.
``batch_read`` wraps that way of reading so the two compositions
share one round trip instead of spending one apiece.  Every producer
of these facts composes them here so consumers see one shape.
"""

from __future__ import annotations

import posixpath

from copy import deepcopy
from typing import Any, Callable, Optional, Union

from ansible_collections.o0_o.posix.plugins.module_utils.group_utils import (
    group_info,
)
from ansible_collections.o0_o.posix.plugins.module_utils.passwd_utils import (
    passwd_info,
)
from ansible_collections.o0_o.posix.plugins.module_utils.path_utils import (
    canonicalize,
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


def _residents_by_home(
    users: dict[str, dict[str, Any]],
) -> dict[str, list[int]]:
    """Map each home path to the UIDs that call it home.

    :param dict[str, dict[str, Any]] users: The o0_users mapping
    :returns dict[str, list[int]]: Resident UIDs per home path
    """
    residents_by_home: dict[str, list[int]] = {}
    for user in users.values():
        home = user.get("home")
        uid = user.get("uid")
        if isinstance(home, str) and home and isinstance(uid, int):
            residents_by_home.setdefault(home, []).append(uid)
    return residents_by_home


def _unread_shells(
    users: dict[str, dict[str, Any]],
    shell_files: dict[str, dict[str, Any]],
) -> set[str]:
    """The shells users hold that no gather has described yet.

    :param dict[str, dict[str, Any]] users: The o0_users mapping
    :param dict[str, dict[str, Any]] shell_files: Shell files already
        described
    :returns set[str]: Shell paths still to read
    """
    return {
        user["shell"]
        for user in users.values()
        if isinstance(user.get("shell"), str)
        and user["shell"]
        and user["shell"] not in shell_files
    }


def batch_read(
    users: dict[str, dict[str, Any]],
    read: ReadPaths,
    known: Optional[dict[str, dict[str, Any]]] = None,
) -> ReadPaths:
    """Read for both compositions at once and serve them from it.

    ``compose_homes`` and ``compose_shell_files`` each read the paths
    they need, and on a remote host each read is round trips of its
    own, even though both sets of paths are settled before either
    composition runs.  This reads their union once, up front, and
    answers with a read that serves the compositions out of that one
    batch.

    Nothing else changes: a path the batch does not cover falls
    through to the caller's own read, as every path does when the
    batch itself fails, so both compositions see what an unbatched
    gather would have given them.  A linked home's target is the path
    that falls through in practice, because a link is only known to
    have one once it has been read.

    ``known`` has to be the same mapping ``compose_shell_files`` will
    be given, or the batch reads shells that composition never asks
    about.

    :param dict[str, dict[str, Any]] users: The o0_users mapping
    :param ReadPaths read: How to read a path's metadata
    :param Optional[dict[str, dict[str, Any]]] known: Shell files a
        previous gather already described
    :returns ReadPaths: A read answering from the batch, falling
        through for whatever the batch does not cover
    """
    paths = sorted(
        set(_residents_by_home(users))
        | _unread_shells(users, dict(known or {}))
    )

    batch: dict[str, Any] = {}
    covered: set[str] = set()

    if paths:
        result = read(paths)
        if not result.get("failed") and isinstance(result.get("paths"), dict):
            batch = result["paths"]
            covered = set(paths)

    def batched(wanted: list[str]) -> dict[str, Any]:
        """Answer for paths the batch holds, reading the rest.

        :param list[str] wanted: Paths to inspect
        :returns dict[str, Any]: The read result shape, carrying one
            entry per known path under its paths key
        """
        if not covered.issuperset(wanted):
            return read(wanted)

        # A composition writes its tags and residents onto what it is
        # handed, so each answer is its own copy rather than the
        # batch's entry
        return {
            "paths": {
                path: deepcopy(batch[path]) for path in wanted if path in batch
            }
        }

    return batched


def _read_entries(
    read: ReadPaths, paths: list[str]
) -> dict[str, Optional[dict[str, Any]]]:
    """Read paths, keeping what the read said about each of them.

    A read answers null for a path that is not there, and that is an
    answer rather than a silence, so it is kept.  A path the read
    never mentioned - and every path, where the read itself failed -
    is left out, because nothing was learned about it.

    :param ReadPaths read: The caller's read
    :param list[str] paths: Paths to inspect
    :returns dict[str, Optional[dict[str, Any]]]: What the read said
        per path, null where the path is not there, empty where the
        read failed
    """
    result = read(paths)
    if result.get("failed") or "paths" not in result:
        return {}
    return {
        path: data
        for path, data in result["paths"].items()
        if data or data is None
    }


def _read_paths(read: ReadPaths, paths: list[str]) -> dict[str, Any]:
    """Read metadata for paths that are there, dropping the rest.

    :param ReadPaths read: The caller's read
    :param list[str] paths: Paths to inspect
    :returns dict[str, Any]: Metadata per path, empty when the read
        failed
    """
    return {
        path: data
        for path, data in _read_entries(read, paths).items()
        if data is not None
    }


def _store_key(path: Any) -> Optional[str]:
    """The o0_paths key a path names, or None where it names none.

    A home is whatever ``/etc/passwd`` wrote in its sixth field, and
    the store is keyed by what a path is rather than by how it was
    written, so the spelling is reduced to that key here.  A field
    that names no path at all - a relative one, or anything that is
    not a string - keys nothing and is dropped rather than repaired,
    because there is no directory to guess at.

    :param Any path: A path as a producer read it
    :returns Optional[str]: The key the store files it under, or None
    """
    if not isinstance(path, str) or not path.startswith("/"):
        return None

    return canonicalize(path)


def _link_key(link: str, target: Any) -> Optional[str]:
    """The o0_paths key a symlink's target names.

    ``ls`` reports a target as the link was written, which is often
    relative to the directory the link lives in, so a relative target
    is resolved against that directory the way the kernel resolves it.

    :param str link: The canonical path of the link itself
    :param Any target: The target as the read reported it
    :returns Optional[str]: The key the store files it under, or None
    """
    if not isinstance(target, str) or not target:
        return None

    if not target.startswith("/"):
        target = posixpath.join(posixpath.dirname(link), target)

    return _store_key(target)


def _add_residents(entry: dict[str, Any], residents: list[int]) -> None:
    """Record UIDs as living at a path they already share.

    :param dict[str, Any] entry: The home entry to add to
    :param list[int] residents: The UIDs to record
    """
    known = entry.get("residents") or []
    entry["residents"] = sorted(set(known) | set(residents))


def _file_home(
    homes: dict[str, Optional[dict[str, Any]]],
    key: str,
    data: Optional[dict[str, Any]],
    residents: list[int],
) -> None:
    """File one read of a home under the key the store gives it.

    Two spellings of one home are one entry, and everyone who wrote
    either of them lives there.  A read that confirmed the home is not
    there files a null, because a dangling home is an answer the store
    keeps rather than a silence - but never over an entry describing a
    home that is there, since a null cannot carry residents and the
    two spellings name one path either way.

    :param dict[str, Optional[dict[str, Any]]] homes: The entries so
        far
    :param str key: The canonical path the entry is filed under
    :param Optional[dict[str, Any]] data: The path's metadata, or None
        where the read confirmed the path is not there
    :param list[int] residents: The UIDs that call the path home
    """
    known = homes.get(key)

    if isinstance(known, dict):
        _add_residents(known, residents)
        return

    if data is None:
        homes.setdefault(key, None)
        return

    data["tags"] = ["posix", "home"]
    data["residents"] = residents
    homes[key] = data


def compose_homes(
    users: dict[str, dict[str, Any]],
    read: ReadPaths,
) -> dict[str, Optional[dict[str, Any]]]:
    """Compose the home entries of the o0_paths store.

    A home is a path, so it is an entry of the one flat path store
    rather than a namespace of its own: keyed by the canonical
    absolute path, carrying the path's own metadata, tagged ``home``,
    and carrying ``residents``, the UIDs that call it home.  Two users
    sharing a home share an entry, however each of them spelled it.
    Where a home is a symlink, the target gets an entry of its own
    carrying the same residents, because that is where their files
    actually are.

    The answer is an observation ``compose_paths`` takes as it stands,
    and it holds to the same three answers the store does.  A home the
    read described is an entry; a home the read confirmed is not there
    is a null, so a user whose home was never made keeps saying so;
    and a home no read reached is left out, because a store reports
    what it asked, not what it assumed.  A home the store cannot key -
    a relative path, or a passwd field that is not a path at all - is
    left out too, rather than filed under a key that would collide
    with the path it is not.

    :param dict[str, dict[str, Any]] users: The o0_users mapping
    :param ReadPaths read: How to read a path's metadata
    :returns dict[str, Optional[dict[str, Any]]]: The home entries,
        keyed by canonical absolute path
    """
    residents_by_home = _residents_by_home(users)

    if not residents_by_home:
        return {}

    homes: dict[str, Optional[dict[str, Any]]] = {}

    for home, data in _read_entries(read, list(residents_by_home)).items():
        key = _store_key(home)
        if key is not None:
            _file_home(homes, key, data, residents_by_home.get(home, []))

    # A home that is a symlink houses its residents at the target
    for home in list(homes):
        entry = homes[home]
        if not isinstance(entry, dict):
            continue

        if entry.get("type") != "link" or "target" not in entry:
            continue

        target = _link_key(home, entry["target"])
        residents = entry.get("residents") or []

        if target is None:
            continue

        if target in homes:
            known = homes[target]
            if isinstance(known, dict):
                _add_residents(known, residents)
            continue

        for path, data in _read_entries(read, [target]).items():
            key = _store_key(path)
            if key is not None:
                _file_home(homes, key, data, residents)

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

    Distinct from the login shells /etc/shells names, which are the
    ``config`` of that path in ``o0_paths``: this fact describes the
    shells users actually hold, named or not.

    :param dict[str, dict[str, Any]] users: The o0_users mapping
    :param ReadPaths read: How to read a path's metadata
    :param Optional[dict[str, dict[str, Any]]] known: Shell files a
        previous gather already described
    :returns dict[str, dict[str, Any]]: The o0_shell_files mapping
    """
    shell_files: dict[str, dict[str, Any]] = dict(known or {})

    unread = _unread_shells(users, shell_files)

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
    "batch_read",
    "compose_homes",
    "compose_shell_files",
    "compose_users_groups",
    "lookup_group",
    "lookup_user",
]
