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
carry that ID as an integer field, membership is expressed in
integer IDs on both sides, and both name their provenance.  The flat
files are the base of that composition and the host's own resolved
view - what ``getent`` answers, where the host has a getent worth
believing - overlays them, so a host that resolves names beyond its
files says so and a host that does not composes what it always did.
``compose_homes`` and
``compose_shell_paths`` define what follows from them, the
directories users live in and the shells they log in with, each
taking the caller's own way of reading a path's metadata.  Both are
paths, so both are entries of the ``o0_paths`` store rather than
namespaces of their own, and both answer in the shape
``compose_paths`` takes.
``batch_read`` wraps that way of reading so the two compositions
share one round trip instead of spending one apiece.  Every producer
of these facts composes them here so consumers see one shape.

Not everything filed under a uid is composed from a file.  A user's
environment and locale are user-scoped facts, and the only user a run
can observe them for is the one it is running as: an environment is
whatever that user's own login files made it.  Reading it once and
filing it under every uid would be one user's answer wearing
everyone's name.

So a producer files them under the effective uid alone, and another
user's are answered by asking as that user - a task with
``become: true`` and ``become_user`` set to them, which reaches this
same composition and merges into the same entry, keyed by the uid
that run turned out to be.  That is the standing discipline for every
user-scoped fact this collection gathers, and the reason ``o0_users``
routinely carries one entry with an environment on it and many
without.
"""

from __future__ import annotations

import posixpath

from copy import deepcopy
from typing import Any, Callable, Optional, Sequence, Union

from ansible_collections.o0_o.core.plugins.module_utils.evidence_utils import (  # noqa: E501
    command_name,
    merge_evidence,
    name_origins,
)
from ansible_collections.o0_o.posix.plugins.module_utils.getent_utils import (
    GETENT_COMMANDS,
)
from ansible_collections.o0_o.posix.plugins.module_utils.group_utils import (
    group_info,
)
from ansible_collections.o0_o.posix.plugins.module_utils.passwd_utils import (
    passwd_info,
)
from ansible_collections.o0_o.posix.plugins.module_utils.path_utils import (
    canonicalize,
)

# What this module is called, which is what a fact it composes names
# as one of the producers that made it
FQCN = "o0_o.posix.users"

Source = Union[str, dict[str, Any], list[dict[str, Any]]]

# What supports an entry's record, by kind of origin: literal paths
# under ``files``, and under ``commands`` the name of each command
# that was consulted.  The third kind of the collection's vocabulary,
# ``config``, is not one these facts are composed from, so it is
# absent here rather than carried empty.
Evidence = dict[str, list[str]]

# How a producer reads metadata for a list of paths: the read action's
# result, carrying one entry per path under its ``paths`` key
ReadPaths = Callable[[list[str]], dict[str, Any]]


def _copy_evidence(evidence: Evidence) -> Evidence:
    """Copy an evidence record so a caller writing to it writes alone.

    :param Evidence evidence: The record to copy
    :returns Evidence: A copy sharing nothing with the original
    """
    return {kind: list(named) for kind, named in evidence.items()}


def _overlay(
    files: dict[str, dict[str, Any]],
    resolved: dict[str, dict[str, Any]],
    path: str,
    command: Sequence[str],
) -> tuple[dict[str, dict[str, Any]], dict[str, Evidence]]:
    """Lay the resolved view over the files parse, keeping provenance.

    The flat files are the base and getent is the overlay, so a host
    that resolves names nowhere but its own files composes exactly
    what it composed before getent was ever asked, and a host that
    resolves them elsewhere gains what its files never said.

    An entry both described is the resolved one where the two
    disagree, because getent is the host's own answer about itself and
    the file is only where part of that answer is written down.  An
    empty field is part of that answer and wins like any other: getent
    reported the field, and what it reported is that there is nothing
    in it.  A null is not - it is the parse having failed to read the
    field at all, which is no answer to prefer - so the base keeps
    what it had rather than losing it to a null.

    Each entry's evidence names the two concretely: the path that was
    read and the command that was consulted, rather than the kind of
    thing either was.  Both kinds are always attempted, so a kind that
    contributed nothing to an entry is empty rather than absent.

    :param dict[str, dict[str, Any]] files: Entries the flat file
        named, keyed by stringified numeric ID
    :param dict[str, dict[str, Any]] resolved: Entries getent named,
        keyed the same, empty where the host has no getent
    :param str path: The flat file that was read
    :param Sequence[str] command: The enumeration that was run, as
        argv
    :returns tuple[dict[str, dict[str, Any]], dict[str, Evidence]]:
        The merged entries, and the evidence for each of them
    """
    merged = {key: dict(entry) for key, entry in files.items()}
    evidence = {key: {"files": [path], "commands": []} for key in files}
    named = [name for name in [command_name(command)] if name]

    for key, entry in resolved.items():
        if key in merged:
            merged[key].update(
                {
                    field: value
                    for field, value in entry.items()
                    if value is not None
                }
            )
            evidence[key]["commands"] = list(named)
        else:
            merged[key] = dict(entry)
            evidence[key] = {"files": [], "commands": list(named)}

    return merged, evidence


def compose_users_groups(
    passwd: Source,
    group: Source,
    getent_passwd: Optional[Source] = None,
    getent_group: Optional[Source] = None,
    passwd_path: str = "/etc/passwd",
    group_path: str = "/etc/group",
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    """Compose the canonical o0_users and o0_groups facts.

    Users are keyed by stringified UID and carry ``name``, ``uid``,
    ``gid`` (the primary group), ``gecos``, ``home``, ``shell``,
    ``groups`` (every GID the user belongs to, primary group
    included), and ``evidence``.  Groups are keyed by stringified GID
    and carry ``name``, ``gid``, ``members`` (the UIDs of every
    member, including those who hold the group as their primary), and
    ``evidence``.

    ``evidence`` names the concrete origins the entry's own record
    came from, by kind: ``files`` holds the path of the flat file that
    named it, which is a key of ``o0_paths`` and joins against it;
    ``commands`` holds the name of the enumeration that resolved it,
    which is what a consumer wants to know - what was consulted -
    where the argv would only repeat what the entry itself answers.
    Both kinds are always present, and a kind that contributed nothing
    to an entry is empty rather than absent, because both are always
    attempted - so a host with no getent says ``commands: []`` rather
    than saying nothing.  At least one origin is named across the two,
    and each kind is sorted and holds one of each name.  The
    vocabulary's third kind, ``config``, is absent: no user or group
    record is composed from a configuration variable.

    Membership does not enter into it: a group's evidence is where its
    own record came from, not where its members' did.  The exception
    is a group no group source named at all, which exists only because
    a passwd entry claimed it as a primary; that one borrows the
    evidence of the users claiming it - the passwd file and the passwd
    enumeration, not the group ones - because they are the whole of
    why it is here.

    getent is optional, and a host without one is not a host with a
    problem: passing nothing for it composes the files-only facts,
    which is what every producer did before there was a resolved view
    to ask for.

    :param Source passwd: ``/etc/passwd`` content or a read/slurp
        result holding it
    :param Source group: ``/etc/group`` content or a read/slurp
        result holding it
    :param Optional[Source] getent_passwd: ``getent passwd``
        enumeration, or None where the host has none
    :param Optional[Source] getent_group: ``getent group``
        enumeration, or None where the host has none
    :param str passwd_path: The path the passwd content was read
        from, which is what its entries name as their origin
    :param str group_path: The path the group content was read from,
        named the same way
    :returns tuple[dict[str, dict[str, Any]], dict[str, dict[str,
        Any]]]: The o0_users and o0_groups mappings
    """
    parsed_groups, group_evidence = _overlay(
        group_info(group, key="id"),
        {} if getent_group is None else group_info(getent_group, key="id"),
        group_path,
        GETENT_COMMANDS["group"],
    )
    parsed_users, user_evidence = _overlay(
        passwd_info(passwd, key="id"),
        {} if getent_passwd is None else passwd_info(getent_passwd, key="id"),
        passwd_path,
        GETENT_COMMANDS["passwd"],
    )

    # A group a group source named owns its own provenance; one only a
    # passwd entry implies borrows the provenance of whoever implies it
    named = set(parsed_groups)

    groups: dict[str, dict[str, Any]] = {
        gid_str: {
            "name": entry.get("name"),
            "gid": int(gid_str),
            "members": [],
            "evidence": _copy_evidence(group_evidence[gid_str]),
        }
        for gid_str, entry in parsed_groups.items()
    }

    users: dict[str, dict[str, Any]] = {}
    uid_by_name: dict[str, int] = {}

    for uid_str, entry in parsed_users.items():
        uid = int(uid_str)
        gid = entry.get("gid")
        name = entry.get("name")
        evidence = _copy_evidence(user_evidence[uid_str])

        users[uid_str] = {
            "name": name,
            "uid": uid,
            "gid": gid,
            "gecos": entry.get("gecos"),
            "home": entry.get("home"),
            "shell": entry.get("shell"),
            "groups": [] if gid is None else [gid],
            "evidence": evidence,
        }

        if isinstance(name, str) and name:
            uid_by_name[name] = uid

        if gid is not None:
            _add_member(groups, gid, uid, evidence, named)

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
            _add_member(groups, gid, uid, users[str(uid)]["evidence"], named)

    return name_origins(users, FQCN), name_origins(groups, FQCN)


def _add_member(
    groups: dict[str, dict[str, Any]],
    gid: int,
    uid: int,
    evidence: Evidence,
    named: set[str],
) -> None:
    """Record a UID as a member of a GID, creating the group entry.

    A primary group that no group source named still exists as far as
    its members are concerned, so it gets an entry with a null name
    rather than being dropped.  Such an entry is here only because a
    user claimed it, so it is that user's evidence it carries - their
    passwd file and their passwd enumeration - folded together with
    every other claimant's.  A group that was named carries its own
    provenance and is left alone.

    :param dict[str, dict[str, Any]] groups: Group mapping to augment
    :param int gid: Group ID gaining the member
    :param int uid: User ID to record
    :param Evidence evidence: Where the record of the user came from
    :param set[str] named: The GIDs a group source named, as
        stringified keys
    """
    gid_str = str(gid)
    entry = groups.setdefault(
        gid_str,
        {
            "name": None,
            "gid": gid,
            "members": [],
            "evidence": {"files": [], "commands": []},
        },
    )
    if uid not in entry["members"]:
        entry["members"].append(uid)

    if gid_str not in named:
        merge_evidence(entry["evidence"], evidence)


def _homes_named(users: dict[str, dict[str, Any]]) -> list[str]:
    """The homes the passwd entries name, as they were written.

    Who lives at each of them is not composed anywhere.  It is the
    join between ``o0_users`` and the store, and a consumer that wants
    it reads the users back against the store - which is what the
    homes lookup does - rather than reading a copy that can drift from
    the field it was copied out of.

    :param dict[str, dict[str, Any]] users: The o0_users mapping
    :returns list[str]: The home paths, one of each, in a settled
        order
    """
    return sorted(
        {
            user["home"]
            for user in users.values()
            if isinstance(user.get("home"), str) and user["home"]
        }
    )


def _described(store: dict[str, Any], path: str) -> bool:
    """Whether the store already holds a path's file metadata.

    A key the store holds for some other reason - the null a command
    lookup files where it missed, the executable row a resolution
    files where it did not - is not a description of the file, so the
    test is for the type a read publishes rather than for the key.

    :param dict[str, Any] store: The o0_paths store as it stands
    :param str path: The path to test
    :returns bool: True where a read has already described the path
    """
    entry = store.get(path)
    return isinstance(entry, dict) and "type" in entry


def _shells_named(
    users: dict[str, dict[str, Any]],
    named: Optional[Sequence[str]] = None,
) -> set[str]:
    """Every login shell this host has given a reason to describe.

    Two reasons, and either is enough.  A shell a passwd entry holds
    is what somebody actually logs in with.  A shell ``/etc/shells``
    names is what the host is willing to call a login shell, whether
    anybody holds it or not - and on a modern Linux that is the only
    reason ``/bin/sh`` gets described at all, because no user's shell
    field says ``/bin/sh`` and it is still the shell the host means by
    the name.

    :param dict[str, dict[str, Any]] users: The o0_users mapping
    :param Optional[Sequence[str]] named: The login shells the host
        names, as ``/etc/shells`` gave them
    :returns set[str]: Shell paths worth describing
    """
    held = {
        user["shell"]
        for user in users.values()
        if isinstance(user.get("shell"), str) and user["shell"]
    }

    return held | {
        shell for shell in (named or []) if isinstance(shell, str) and shell
    }


def _unread_shells(
    users: dict[str, dict[str, Any]],
    store: dict[str, Any],
    named: Optional[Sequence[str]] = None,
) -> set[str]:
    """The login shells no gather has described yet.

    :param dict[str, dict[str, Any]] users: The o0_users mapping
    :param dict[str, Any] store: The o0_paths store as it stands
    :param Optional[Sequence[str]] named: The login shells the host
        names
    :returns set[str]: Shell paths still to read
    """
    return {
        shell
        for shell in _shells_named(users, named)
        if not _described(store, shell)
    }


def batch_read(
    users: dict[str, dict[str, Any]],
    read: ReadPaths,
    known: Optional[dict[str, Any]] = None,
    named: Optional[Sequence[str]] = None,
) -> ReadPaths:
    """Read for both compositions at once and serve them from it.

    ``compose_homes`` and ``compose_shell_paths`` each read the paths
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

    ``known`` and ``named`` have to be the same store and the same
    list ``compose_shell_paths`` will be given, or the batch reads
    shells that composition never asks about and misses shells it
    does.

    :param dict[str, dict[str, Any]] users: The o0_users mapping
    :param ReadPaths read: How to read a path's metadata
    :param Optional[dict[str, Any]] known: The o0_paths store a
        previous gather already published
    :param Optional[Sequence[str]] named: The login shells the host
        names, as ``/etc/shells`` gave them
    :returns ReadPaths: A read answering from the batch, falling
        through for whatever the batch does not cover
    """
    paths = sorted(
        set(_homes_named(users))
        | _unread_shells(users, dict(known or {}), named)
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

        # A composition writes onto what it is handed, so each answer
        # is its own copy rather than the batch's entry
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


def _file_home(
    homes: dict[str, Optional[dict[str, Any]]],
    key: str,
    data: Optional[dict[str, Any]],
) -> None:
    """File one read of a home under the key the store gives it.

    Two spellings of one home are one entry, however each of them was
    written.  A read that confirmed the home is not there files a
    null, because a dangling home is an answer the store keeps rather
    than a silence - but never over an entry describing a home that is
    there, since the two spellings name one path either way and the
    path either is there or is not.

    :param dict[str, Optional[dict[str, Any]]] homes: The entries so
        far
    :param str key: The canonical path the entry is filed under
    :param Optional[dict[str, Any]] data: The path's metadata, or None
        where the read confirmed the path is not there
    """
    if isinstance(homes.get(key), dict):
        return

    if data is None:
        homes.setdefault(key, None)
        return

    homes[key] = data


def compose_homes(
    users: dict[str, dict[str, Any]],
    read: ReadPaths,
) -> dict[str, Optional[dict[str, Any]]]:
    """Compose the home entries of the o0_paths store.

    A home is a path, so it is an entry of the one flat path store
    rather than a namespace of its own: keyed by the canonical
    absolute path and carrying the path's own metadata.  Two users
    sharing a home share an entry, however each of them spelled it.
    Who lives there is not stored: it is the join between the users
    and the store, and the homes lookup makes it from the field
    ``o0_users`` already carries.

    Every step a home resolves through gets an entry of its own, the
    way a shell's does, because a home reached through a link is where
    the user's files actually are.

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
    named = _homes_named(users)

    if not named:
        return {}

    homes: dict[str, Optional[dict[str, Any]]] = {}

    for home, data in _read_entries(read, named).items():
        key = _store_key(home)
        if key is not None:
            _file_home(homes, key, data)

    # Whatever a home is reached through is a path the user's files
    # are behind, so every step of the chain is an entry too. The
    # steps are read in one batch, because a chain is not known until
    # the home has been read
    hops = sorted(
        {
            hop
            for home, entry in homes.items()
            if isinstance(entry, dict)
            for hop in _home_hops(home, entry)
            if hop not in homes
        }
    )

    if hops:
        for path, data in _read_entries(read, hops).items():
            key = _store_key(path)
            if key is not None:
                _file_home(homes, key, data)

    return homes


def _home_hops(home: str, entry: dict[str, Any]) -> list[str]:
    """The paths a home is reached through, beyond the home itself.

    A read that walked the chain says every step of it; one that did
    not still reports a link's target, which is the one step it knows.

    :param str home: The canonical path of the home
    :param dict[str, Any] entry: What the read said about it
    :returns list[str]: The keys the steps file under
    """
    steps = [step for step in _chain_keys(entry) if step != home]

    if steps or entry.get("type") != "link":
        return steps

    target = _link_key(home, entry.get("target"))

    return [target] if target is not None else []


def compose_shell_paths(
    users: dict[str, dict[str, Any]],
    read: ReadPaths,
    known: Optional[dict[str, Any]] = None,
    named: Optional[Sequence[str]] = None,
) -> dict[str, Optional[dict[str, Any]]]:
    """Compose the shell entries of the o0_paths store.

    A login shell is a file, so it is an entry of the one flat path
    store the way a home is: keyed by the canonical absolute path and
    carrying what a read of that path says - its type, its mode and
    the bits of it, who owns it, when it changed, and for a link the
    target the listing reported.

    Two reasons put a shell here and either is enough: a passwd entry
    holds it, or ``/etc/shells`` names it.  Reading only what users
    hold would leave out the one shell a consumer is most likely to
    ask about, because on a modern Linux nobody's shell field says
    ``/bin/sh`` and ``/bin/sh`` is still what the host means by the
    name.  The file's own list is the ``config`` of its own entry,
    which is the host's claim rather than a description of any file.

    Every hop the shell resolves through gets an entry of its own, for
    the reason a linked home's target does: the question a consumer
    has about ``/bin/sh`` is what it really is, and a chain that named
    ``/usr/bin/bash`` without describing it would answer half of it.
    The hops are read in one batch after the shells, because a chain
    is not known until the shell has been read.

    A shell the store already describes is left as it stands rather
    than read again, so a run adds to what an earlier gather published
    instead of paying for it twice.

    :param dict[str, dict[str, Any]] users: The o0_users mapping
    :param ReadPaths read: How to read a path's metadata
    :param Optional[dict[str, Any]] known: The o0_paths store a
        previous gather already published
    :returns dict[str, Optional[dict[str, Any]]]: The shell entries,
        keyed by canonical absolute path
    """
    store = dict(known or {})
    unread = _unread_shells(users, store, named)

    if not unread:
        return {}

    shells: dict[str, Optional[dict[str, Any]]] = {}

    for path, data in _read_entries(read, sorted(unread)).items():
        key = _store_key(path)
        if key is not None:
            shells[key] = data

    # Every step of every chain, read once, in one batch. A step the
    # store or this composition already describes is not read again
    hops = sorted(
        {
            hop
            for entry in shells.values()
            if isinstance(entry, dict)
            for hop in _chain_keys(entry)
            if hop not in shells and not _described(store, hop)
        }
    )

    if hops:
        for path, data in _read_entries(read, hops).items():
            key = _store_key(path)
            if key is not None and key not in shells:
                shells[key] = data

    return shells


def _chain_keys(entry: dict[str, Any]) -> list[str]:
    """The o0_paths keys a resolution chain names.

    :param dict[str, Any] entry: A read's entry for one path
    :returns list[str]: The keys the chain's steps file under
    """
    chain = entry.get("resolution")

    if not isinstance(chain, list):
        return []

    keys = [_store_key(step) for step in chain]

    return [key for key in keys if key is not None]


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
    "compose_shell_paths",
    "compose_users_groups",
    "lookup_group",
    "lookup_user",
]
