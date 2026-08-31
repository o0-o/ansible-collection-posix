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

Every composed entry names who composed it and what they consulted.
``origin`` is a sorted list of the module FQCNs that contributed it -
one field, one meaning, and a collection contributing to this store
names itself there rather than inventing a field of its own.
``evidence`` is the collection's one provenance vocabulary, keyed by
kind, naming the paths that were read and the commands that were run
for this entry in particular, because what produced one path's entry
is rarely what produced another's.  Both accumulate where every other
field is replaced, because two producers that both described a path
both belong in them.

``canonicalize`` reduces an absolute path to the one form the store
keys it by, for the producers and consumers that have to write a key
rather than read one, and ``flags_to_octal_mode`` parses the
permission flags an ``ls`` line carries, for the producers that fill
an entry in.  ``normalize_mode`` reads a mode the other way, from the
raw argument a task wrote to the octal string a command takes.
"""

from __future__ import annotations

import posixpath

from typing import Any, Optional

from ansible_collections.o0_o.posix.plugins.module_utils.evidence_utils import (  # noqa: E501
    EVIDENCE,
    merge_evidence,
)

# The key an entry names the producers that composed it under
ORIGIN = "origin"


def canonicalize(path: str) -> str:
    """Reduce an absolute path to the one form the store keys it by.

    The store keys a path by what it is rather than by how it was
    written, so a trailing slash, a doubled separator, and a ``.`` or
    ``..`` component all collapse into the same key here.  A leading
    ``//`` is the one form ``posixpath`` keeps and the store refuses,
    so it collapses too.

    This repairs what ``_validate_path`` refuses, and the two are
    meant to be used that way round: a caller holding a path a host
    wrote canonicalizes it before it becomes a key, and the store
    itself never guesses which of two spellings was meant.

    :param str path: An absolute path as it was written
    :returns str: The path in the form the o0_paths store keys
    """
    canonical = posixpath.normpath(path)
    while canonical.startswith("//"):
        canonical = canonical[1:]
    return canonical


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


def normalize_mode(mode: Any) -> Optional[str]:
    """Render a requested mode in the octal string form chmod reads.

    A mode is a raw argument, so an unquoted YAML scalar reaches a
    task as an integer: ``mode: 0`` arrives as int 0, and ``mode:
    0644`` as int 420, YAML having read the leading zero as octal
    already.  An integer is a mode's numeric value, which is how the
    builtin file modules read one -- ``set_mode_if_different`` hands
    an int straight to ``chmod(2)`` and renders it back with
    ``'0%03o'`` -- so that same rendering is what this returns, and a
    quoted mode is left exactly as it was written.

    Mode 0 is a mode.  Only an unset mode is unset, so ``None`` passes
    through unchanged and the callers downstream ask whether the mode
    is None rather than whether it is true.

    :param Any mode: A mode as the argument spec received it
    :returns Optional[str]: The mode in octal string form, or None
    :raises ValueError: If the mode is negative or is neither a string
        nor an integer
    """
    if mode is None:
        return None

    if isinstance(mode, str):
        # An empty string is not an unset mode, and it is not a mode
        # either; the builtin file modules refuse it the same way
        if not mode:
            raise ValueError("Mode must not be empty")
        return mode

    if isinstance(mode, int):
        if mode < 0:
            raise ValueError(f"Mode must not be negative, got {mode}")
        return "0%03o" % mode

    raise ValueError(
        "Mode must be an octal string or an integer, got "
        f"{type(mode).__name__}: {mode!r}"
    )


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

    if ORIGIN in composed:
        named = composed[ORIGIN]
        if not isinstance(named, list) or not all(
            isinstance(name, str) for name in named
        ):
            raise ValueError(
                f"The origin of {path!r} must be a list of the module"
                f" names that composed the entry, got"
                f" {type(named).__name__}: {named!r}"
            )
        composed[ORIGIN] = sorted(set(named))

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


def _name_origin(entry: Any, origin: Optional[str]) -> Any:
    """Put a producer's name on an entry it composed.

    A null carries no fields, so a path confirmed absent names no
    producer; what it says is that somebody asked, and the entry that
    says who is the one that describes something.

    :param Any entry: The entry as the producer composed it
    :param Optional[str] origin: The producer's module FQCN, or None
        where the caller composes on somebody else's behalf
    :returns Any: The entry, named
    """
    if origin is None or not isinstance(entry, dict):
        return entry

    named = list(entry.get(ORIGIN) or [])
    named.append(origin)
    entry[ORIGIN] = sorted(set(named))

    return entry


def compose_paths(
    store: Optional[dict[str, Any]] = None,
    observation: Optional[dict[str, Any]] = None,
    origin: Optional[str] = None,
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

    ``origin`` and ``evidence`` are the exceptions the rule needs.
    They are the record of who looked and what they consulted, not
    part of the observation, and two producers that both described a
    path both belong in them, so both accumulate where every other
    field is replaced.  A caller passing its own module FQCN names
    itself on every entry it just observed; a caller composing on
    somebody else's behalf passes none and the entries keep whatever
    names they arrived with.

    :param Optional[dict[str, Any]] store: The o0_paths fact as it
        stands, or None before anything has been observed
    :param Optional[dict[str, Any]] observation: What was just
        observed about some paths, keyed the same way
    :param Optional[str] origin: The FQCN of the module composing the
        observation, named on every entry it describes
    :returns dict[str, Optional[dict[str, Any]]]: The composed store
    :raises ValueError: If either mapping is keyed by anything but a
        flat absolute path, carries an entry that is neither null nor
        a mapping of observed facts, or nests a path store under an
        entry
    """
    composed = _validate_paths(store, "store")

    for path, entry in _validate_paths(observation, "observation").items():
        known = composed.get(path)
        entry = _name_origin(entry, origin)
        if isinstance(known, dict) and isinstance(entry, dict):
            named = sorted(
                set(known.get(ORIGIN) or []) | set(entry.get(ORIGIN) or [])
            )
            if named:
                entry[ORIGIN] = named
            consulted = known.get(EVIDENCE)
            if isinstance(consulted, dict):
                merged = {
                    kind: (
                        list(named) if isinstance(named, list) else dict(named)
                    )
                    for kind, named in consulted.items()
                }
                found = entry.get(EVIDENCE)
                if isinstance(found, dict):
                    merge_evidence(merged, found)
                entry[EVIDENCE] = merged
        composed[path] = entry

    return composed


__all__ = [
    "ORIGIN",
    "canonicalize",
    "compose_paths",
    "flags_to_octal_mode",
]
