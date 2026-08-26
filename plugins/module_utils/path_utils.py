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

"""The o0_paths fact store and the path helpers around it.

``compose_paths`` is the one way ``o0_paths`` is built or added to.
The fact is flat absolute-path keys, forever: a path is a key of its
own, never a branch another path hangs from, and a directory names
its contents as a list of path references rather than nesting them
underneath it.  Recursion, link following, and a parent walk all add
entries beside the ones already there, so the same path is one entry
however it was reached.

Absence and emptiness are three different answers, collection-wide.
A key absent from the store was never asked about; a key whose value
is null was asked about and does not exist; a typed empty (``''``,
``[]``, ``{}``) exists and is empty.  Nothing here converts one of
those answers into another.

``flags_to_octal_mode`` parses the permission flags an ``ls`` line
carries, for the producers that fill an entry in.
"""

from __future__ import annotations

from typing import Any, Optional


def flags_to_octal_mode(flags: str) -> str:
    """Convert ls permission flags to octal mode string.

    Parses the 10-character permission string from ls output
    (e.g., "-rwxr-xr-x") and converts it to a 4-digit octal
    mode string (e.g., "0755").

    :param str flags: Permission flags from ls (10 characters)
    :returns str: Octal mode as 4-digit string (e.g., "0755")
    """
    if not flags or len(flags) < 10:
        return "0000"

    perms = flags[1:]  # Skip first char (file type)
    octal = 0

    # Owner permissions
    if perms[0] == "r":
        octal += 0o400
    if perms[1] == "w":
        octal += 0o200
    if perms[2] in ["x", "s", "S"]:
        octal += 0o100
    if perms[2] in ["s", "S"]:
        octal += 0o4000  # setuid

    # Group permissions
    if perms[3] == "r":
        octal += 0o040
    if perms[4] == "w":
        octal += 0o020
    if perms[5] in ["x", "s", "S"]:
        octal += 0o010
    if perms[5] in ["s", "S"]:
        octal += 0o2000  # setgid

    # Other permissions
    if perms[6] == "r":
        octal += 0o004
    if perms[7] == "w":
        octal += 0o002
    if perms[8] in ["x", "t", "T"]:
        octal += 0o001
    if perms[8] in ["t", "T"]:
        octal += 0o1000  # sticky bit

    return f"{octal:04o}"


def _validate_path(path: Any, role: str) -> None:
    """Fail unless a value is a flat, absolute, canonical path.

    The store is keyed by what a path is, not by how a caller wrote
    it, so a relative path, an unexpanded ``~``, a trailing slash, a
    doubled separator, and a ``.`` or ``..`` component are all
    refused rather than repaired: each of them is a second way to
    write a path the store already has a key for.

    :param Any path: The candidate path
    :param str role: How the path is being used, named for the
        message, e.g. 'An o0_paths key'
    :raises ValueError: If the path cannot key the flat store
    """
    if not isinstance(path, str):
        raise ValueError(
            f"{role} must be a string, got {type(path).__name__}: {path!r}"
        )

    if not path:
        raise ValueError(f"{role} must not be empty")

    if not path.startswith("/"):
        raise ValueError(
            f"{role} must be an absolute path, got {path!r}."
            f" A relative path or an unexpanded '~' names nothing"
            f" on its own"
        )

    if path == "/":
        return

    if path.endswith("/"):
        raise ValueError(
            f"{role} must not end in '/', got {path!r}."
            f" A trailing slash keys the same path twice"
        )

    for component in path.split("/")[1:]:
        if not component:
            raise ValueError(
                f"{role} must not contain an empty path component,"
                f" got {path!r}"
            )
        if component in (".", ".."):
            raise ValueError(
                f"{role} must be canonical, got {path!r}."
                f" A '{component}' component keys the same path twice"
            )


def _validate_entry(path: str, entry: Any) -> Optional[dict[str, Any]]:
    """Fail unless a value is a null or a path's observed facts.

    A field named like a path is a nested store, which is the shape
    ``o0_paths`` exists in order not to have, and ``children`` is a
    list of references to keys of the store rather than the entries
    themselves.

    :param str path: The path the entry describes, for the message
    :param Any entry: The candidate entry
    :returns Optional[dict[str, Any]]: The entry, copied shallowly so
        the store and its producer do not share one mapping, or None
    :raises ValueError: If the entry is neither null nor a mapping of
        observed facts, or nests paths under itself
    """
    if entry is None:
        return None

    if not isinstance(entry, dict):
        raise ValueError(
            f"The o0_paths entry for {path!r} must be a mapping of"
            f" observed facts, or null where the path does not exist,"
            f" got {type(entry).__name__}: {entry!r}"
        )

    for field in entry:
        if not isinstance(field, str):
            raise ValueError(
                f"The o0_paths entry for {path!r} has a field named"
                f" {field!r}, which is not a string"
            )
        if field.startswith("/"):
            raise ValueError(
                f"The o0_paths entry for {path!r} has a field named"
                f" {field!r}, which is a path. The store is flat:"
                f" every path is a key of its own"
            )

    composed = dict(entry)

    if "children" in composed:
        children = composed["children"]
        if not isinstance(children, list):
            raise ValueError(
                f"The children of {path!r} must be a list of path"
                f" references, got {type(children).__name__}:"
                f" {children!r}"
            )
        for child in children:
            _validate_path(
                child,
                f"A children reference of {path!r}",
            )
        composed["children"] = list(children)

    return composed


def _validate_paths(source: Any, role: str) -> dict[str, Any]:
    """Fail unless a mapping is a usable o0_paths store.

    :param Any source: The candidate store or observation
    :param str role: Which argument it is, named for the message
    :returns dict[str, Any]: The validated mapping, entries copied
    :raises ValueError: If the mapping, any key, or any entry does
        not hold to the store's shape
    """
    if source is None:
        return {}

    if not isinstance(source, dict):
        raise ValueError(
            f"The o0_paths {role} must be a mapping of paths to what"
            f" was observed about them, got"
            f" {type(source).__name__}: {source!r}"
        )

    composed: dict[str, Any] = {}
    for path, entry in source.items():
        _validate_path(path, f"An o0_paths key in the {role}")
        composed[path] = _validate_entry(path, entry)

    return composed


def compose_paths(
    store: Optional[dict[str, Any]] = None,
    observation: Optional[dict[str, Any]] = None,
) -> dict[str, Optional[dict[str, Any]]]:
    """Compose the canonical o0_paths fact store.

    Every merge into ``o0_paths`` goes through here.  The store is
    flat absolute-path keys, forever: a key is a whole path and
    nothing about a path is filed under another path.  A directory
    names its contents in a ``children`` list of path references, and
    each of those paths gets an entry of its own if and when it is
    observed, so recursion and link following widen the store rather
    than deepen it.  Both arguments are held to that shape, which is
    what keeps a store composed here composable here again.

    An entry is what one observation had to say about a path, and the
    newest observation of a path wins whole.  Fields are not blended
    across observations: a store that mixed a mode read before a
    chmod with a size read after it would describe a file that never
    existed.  A producer with more to say about a path says all of it
    at once.

    Three answers are kept apart, per the collection's absence
    contract.  A path absent from the store was never asked about; a
    path whose entry is null was asked about and does not exist; a
    typed empty (``''``, ``[]``, ``{}``) exists and is empty.  A null
    observation overwrites the entry the store held, which is how a
    deletion is recorded, and an entry observed for a path the store
    held as null resurrects it the same way.  A path the observation
    does not mention is left as it was, so a gather that asked about
    one path does not report the rest of the filesystem as gone, and
    a null is never rounded to an empty mapping in either direction.

    :param Optional[dict[str, Any]] store: The o0_paths fact as it
        stands, or None before anything has been observed
    :param Optional[dict[str, Any]] observation: What was just
        observed about some paths, keyed the same way
    :returns dict[str, Optional[dict[str, Any]]]: The composed store
    :raises ValueError: If either mapping is keyed by anything but a
        flat absolute path, carries an entry that is neither null nor
        a mapping of observed facts, or nests a path store under an
        entry
    """
    composed = _validate_paths(store, "store")
    composed.update(_validate_paths(observation, "observation"))
    return composed


__all__ = [
    "compose_paths",
    "flags_to_octal_mode",
]
