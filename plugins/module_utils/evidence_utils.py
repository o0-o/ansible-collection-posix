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

"""The one vocabulary a fact names its provenance in.

Every fact this collection composes says where it came from under
``evidence``, a mapping keyed by kind of origin, and the kinds are the
same three wherever it appears.  ``files`` holds the paths that were
read, each a key of ``o0_paths``.  ``commands`` holds the names of the
commands that were consulted.  ``config`` holds the POSIX
configuration variables that were read, mapped to the values the host
answered with, keyed and typed the way ``o0_os.config`` keys and types
them.

Kind by key, never by element shape: a consumer reads the kind off the
key it asked for rather than off what it finds there, so a kind added
later breaks nobody, and a producer with none of a kind says so by
leaving the key off rather than by carrying it empty.

A command is named, not spelled out.  Argv would say what was typed,
and what was typed is a debugging concern rather than a fact: the
configuration sweep is dozens of invocations of one command, and
gathering a directory's worth of file metadata is one invocation per
file.  Either would bury the answer under its own repetitions.  The
name answers the question a consumer actually has, which is what was
consulted, and the answer to what it said is the fact itself.

Which is also why a value appears here at all only when it evidences
something else.  ``config`` carries a variable's value because a
compliance verdict is a claim about the host that the variable
supports; ``o0_os.config`` publishes those same variables as the fact
they are, and a fact is not evidence for itself.
"""

from __future__ import annotations

import posixpath

from typing import Any, Iterable, Optional, Union

# The key a fact names its provenance under, everywhere
EVIDENCE = "evidence"

# The whole vocabulary.  A producer names its origins in these and a
# datum that is none of them is a finding rather than an origin, and
# belongs beside the verdict it is part of.
EVIDENCE_KINDS = ("files", "commands", "config")

# What an entry's provenance looks like: lists of strings under
# ``files`` and ``commands``, a mapping under ``config``
Evidence = dict[str, Any]


def command_name(command: Union[str, Iterable[Any], None]) -> Optional[str]:
    """The name a command is known by, or None where it names none.

    Argv's first word is the command; everything after it is what the
    command was asked, which the fact itself answers.  The name is
    that word's base name, so a probe that resolved to a path is
    filed under the command it is rather than under where it was
    found.

    A command written as a string is a shell reading it back rather
    than a command being run, which the raw quoting contract already
    settled, so it names nothing here and the producer that ran it
    names what it ran.

    :param Union[str, Iterable[Any], None] command: A command as a
        request carried it
    :returns Optional[str]: The name, or None
    """
    if isinstance(command, str) or command is None:
        return None

    argv = list(command)
    if not argv or not isinstance(argv[0], str) or not argv[0].strip():
        return None

    return posixpath.basename(argv[0].strip())


def compose_evidence(
    files: Optional[Iterable[str]] = None,
    commands: Optional[Iterable[Optional[str]]] = None,
    config: Optional[dict[str, Any]] = None,
) -> Evidence:
    """Build an evidence record naming the kinds it was handed.

    A kind passed as an empty collection was attempted and answered
    for nothing, and says so.  A kind not passed at all is one this
    producer does not have, and is left off.

    :param Optional[Iterable[str]] files: Paths that were read
    :param Optional[Iterable[Optional[str]]] commands: Names of the
        commands that were consulted, nulls dropped
    :param Optional[dict[str, Any]] config: Configuration variables
        that were read, mapped to what the host answered
    :returns Evidence: The record
    """
    record: Evidence = {}

    if files is not None:
        record["files"] = sorted(set(files))

    if commands is not None:
        record["commands"] = sorted({name for name in commands if name})

    if config is not None:
        record["config"] = dict(config)

    return record


def commands_run(
    cmds_completed: Iterable[Any],
    *types: str,
) -> list[str]:
    """The names of the commands a batch ran for the given types.

    A producer names the request types it owns and reads back what
    actually ran for them, so what a fact says was consulted cannot
    drift from what the command spec asks for.

    :param Iterable[Any] cmds_completed: Command results, each
        carrying the type it was requested under and the command it
        ran
    :param str types: The request types this producer owns
    :returns list[str]: The command names, sorted and one of each
    """
    wanted = set(types)

    return sorted(
        {
            name
            for result in cmds_completed
            if isinstance(result, dict) and result.get("type") in wanted
            for name in [command_name(result.get("command"))]
            if name
        }
    )


def merge_evidence(into: Evidence, evidence: Evidence) -> None:
    """Fold one evidence record into another, once each.

    Evidence accumulates: two producers that answered for one entry
    both named it, and a merge that let the later one replace the
    earlier would publish an entry claiming half of what put it there.
    A list keeps one of each name, sorted; a mapping keeps the first
    answer for a variable, because a variable read twice in one gather
    was read from one host.

    :param Evidence into: The record to add to, edited in place
    :param Evidence evidence: The record whose origins are added
    """
    for kind, named in evidence.items():
        if isinstance(named, dict):
            known = into.setdefault(kind, {})
            for variable, value in named.items():
                known.setdefault(variable, value)
            continue

        origins = into.setdefault(kind, [])
        for origin in named:
            if origin not in origins:
                origins.append(origin)
        origins.sort()


def merge_entry(into: dict[str, Any], entry: dict[str, Any]) -> None:
    """Merge one producer's entry into another's, keeping evidence.

    The later producer wins every field it names, which is what a
    merge means here, except its provenance: two producers that
    answered for one entry both belong in it.

    :param dict[str, Any] into: The entry to add to, edited in place
    :param dict[str, Any] entry: The entry being merged in
    """
    known = into.get(EVIDENCE)
    named = entry.get(EVIDENCE)

    if isinstance(known, dict) and isinstance(named, dict):
        merge_evidence(known, named)
        entry = {key: value for key, value in entry.items() if key != EVIDENCE}

    into.update(entry)


__all__ = [
    "EVIDENCE",
    "EVIDENCE_KINDS",
    "command_name",
    "commands_run",
    "compose_evidence",
    "merge_entry",
    "merge_evidence",
]
