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

"""What the shell says about the process it hands you.

Two facts a shell knows and nothing else on the host does: the
resource limits in force, and the mask the process will create files
under.  Both belong to a user rather than to a machine.  Effective
limits differ per user by design - ``pam_limits`` grants them per user
and per group, BSD hands them out by login class, and root's ceiling
is not anyone else's - and a umask is whatever the login files of the
user who is logged in set it to.  So they file under
``o0_users[<uid>]`` beside the environment and the locale, and they
describe the one user the play connects as.  Another user's are
answered by a run delegated to that user, not by reading this one's.

``ulimit`` is a shell builtin, so it is asked through ``sh``, and the
soft and hard sets are asked in the one invocation.

Neither the option letters nor the labels ``ulimit -a`` prints are
portable, and the letters are the worse of the two.  ``-p`` is the
pipe buffer under bash and the process count under dash; ``-u`` is the
process count under bash and unknown to dash; ``-x`` is the file lock
count under bash and ``-w`` is under dash.  A fact keyed by the letter
would file two different resources under one name and be wrong about
one of them on every host.

The labels are shell-specific too, but they are self-describing, and
a table built from what the shells actually print maps them onto one
set of names.  Five styles are known to it: bash's
``core file size (blocks, -c)``, ash's ``core file size (blocks)``,
dash's glued ``coredump(blocks)``, ksh's
``core file size (blocks)   (-c)`` and zsh's leading
``-c: core file size (blocks)``.  A label the table does not know
keeps its own words rather than being dropped or guessed at, so a
shell nobody here has run still answers something true.

The parenthetical the label carries is the unit, and it is kept.  The
same resource is reported in blocks by one shell and kilobytes by
another, and a number with no unit beside it would be a number a
consumer could only misread.

A limit the shell prints as ``unlimited`` is present and null: the
resource is there and has no ceiling.  A limit it prints as
``not supported`` or ``undefined`` is absent: the shell has said it
will not answer, which is not the same as answering that there is no
limit.
"""

from __future__ import annotations

import re

from typing import Any, Optional

from ansible_collections.o0_o.core.plugins.module_utils import (
    process_all_command_results,
)

# The markers the probe prints between the two sets
LIMITS_SOFT_MARKER = "@SOFT@"
LIMITS_HARD_MARKER = "@HARD@"

# What a shell prints for a resource it has and does not cap
LIMITS_UNLIMITED = "unlimited"

# One name per resource, mapped from the labels the shells print.
# Every key here was read off a running host rather than a manpage.
LIMITS_MAPPING = {
    # cpu time
    "cpu time": "cpu_time",
    "time": "cpu_time",
    # file size
    "file size": "file_size",
    "file": "file_size",
    # data segment
    "data seg size": "data",
    "data size": "data",
    "data": "data",
    # stack
    "stack size": "stack",
    "stack": "stack",
    # core dumps
    "core file size": "core",
    "coredump": "core",
    # resident set
    "max memory size": "memory",
    "memory": "memory",
    # locked pages
    "max locked memory": "locked_memory",
    "locked memory": "locked_memory",
    "locked address space": "locked_memory",
    "locked-in-memory size": "locked_memory",
    # processes
    "max user processes": "processes",
    "process": "processes",
    "processes": "processes",
    "nproc": "processes",
    # descriptors
    "open files": "open_files",
    "nofiles": "open_files",
    "nofile": "open_files",
    "file descriptors": "open_files",
    # address space
    "virtual memory": "virtual_memory",
    "vmemory": "virtual_memory",
    "address space": "virtual_memory",
    "process size": "virtual_memory",
    # locks
    "file locks": "file_locks",
    "locks": "file_locks",
    # priorities
    "real-time priority": "realtime_priority",
    "rtprio": "realtime_priority",
    "scheduling priority": "scheduling_priority",
    "nice": "scheduling_priority",
    # the rest, each named by one shell only
    "pending signals": "pending_signals",
    "sigpend": "pending_signals",
    "posix message queues": "message_queues",
    "message queue size": "message_queues",
    "pipe size": "pipe",
    "pipe buffer size": "pipe",
    "socket buffer size": "socket_buffer",
    "swap size": "swap",
    "threads": "threads",
}

# A leading option letter, which zsh prints and nobody else does
_LEADING_OPTION = re.compile(r"^-[A-Za-z]:\s*")

# Whatever a label carries in parentheses, which is its unit and,
# where the shell prints one, the option letter that asks for it
_PARENTHETICAL = re.compile(r"\(([^)]*)\)")

# The option letter riding along inside the unit
_OPTION_IN_UNIT = re.compile(r"\s*,?\s*-[A-Za-z]$")


def _split_limit_line(line: str) -> Optional[tuple[str, Optional[str], str]]:
    """Split one ``ulimit -a`` line into label, unit and value.

    The value is the last word, and it is only a value where it is a
    number or the word a shell uses for no ceiling.  ``not supported``
    ends in a word that is neither, which is how a resource the shell
    will not answer for is told from one it answered.

    :param str line: One line of ``ulimit -a`` output
    :returns Optional[tuple[str, Optional[str], str]]: The normalized
        label, the unit where the shell named one, and the value, or
        None where the line carries no value
    """
    stripped = line.strip()
    if not stripped:
        return None

    head, _space, value = stripped.rpartition(" ")
    if not head:
        return None

    value = value.strip()
    if value != LIMITS_UNLIMITED and not value.isdigit():
        return None

    head = _LEADING_OPTION.sub("", head)

    units = [
        _OPTION_IN_UNIT.sub("", found).strip()
        for found in _PARENTHETICAL.findall(head)
    ]
    unit = next((found for found in units if found), None)

    label = " ".join(_PARENTHETICAL.sub(" ", head).split()).lower()
    if not label:
        return None

    return label, unit, value


def _parse_limit_set(text: str) -> dict[str, dict[str, Any]]:
    """Read one ``ulimit -a`` set into a resource per line.

    :param str text: One set's lines
    :returns dict[str, dict[str, Any]]: Each resource's value and
        unit, keyed by the name the mapping gave it
    """
    resources: dict[str, dict[str, Any]] = {}

    for line in text.splitlines():
        split = _split_limit_line(line)
        if split is None:
            continue

        label, unit, value = split
        name = LIMITS_MAPPING.get(label, label.replace(" ", "_"))

        # Two labels the table maps onto one name would file one
        # resource over another, so the second keeps its own words
        if name in resources:
            name = label.replace(" ", "_")
            if name in resources:
                continue

        resources[name] = {
            "value": None if value == LIMITS_UNLIMITED else int(value),
            "unit": unit,
        }

    return resources


def _parse_ulimit(
    output: str,
    e_prefix: str,
) -> tuple[Optional[dict[str, Any]], Optional[list[Exception]]]:
    """Canonical COMMAND_SPEC parser for the resource limits probe.

    Answers with a resource per limit, each carrying the soft ceiling
    in force, the hard ceiling it may be raised to, and the unit the
    shell reported them in.  A resource only one of the two sets named
    carries a null for the other, because a shell that answered one
    and not the other has not said the missing one is unlimited.

    :param str output: Raw stdout of the probe
    :param str e_prefix: Error prefix for context
    :returns tuple[Optional[dict[str, Any]], Optional[list[Exception]]]:
        The limits keyed by resource, and never an error
    """
    del e_prefix  # a shell that will not say is not a fault

    text = output or ""
    if LIMITS_SOFT_MARKER not in text:
        return None, None

    _before, _marker, rest = text.partition(LIMITS_SOFT_MARKER)
    soft_text, _marker, hard_text = rest.partition(LIMITS_HARD_MARKER)

    soft = _parse_limit_set(soft_text)
    hard = _parse_limit_set(hard_text)

    limits: dict[str, Any] = {}
    for name in list(soft) + [name for name in hard if name not in soft]:
        entry = soft.get(name) or hard.get(name) or {}
        limits[name] = {
            "soft": (soft.get(name) or {}).get("value"),
            "hard": (hard.get(name) or {}).get("value"),
        }
        if entry.get("unit"):
            limits[name]["unit"] = entry["unit"]

    return (limits or None), None


def _parse_umask(
    output: str,
    e_prefix: str,
) -> tuple[Optional[str], Optional[list[Exception]]]:
    """Canonical COMMAND_SPEC parser for the umask probe.

    Answers in the four-character octal form the collection writes
    every mode in, because zsh prints three digits where every other
    shell prints four and a mask is not two shapes.

    :param str output: Raw stdout of ``umask``
    :param str e_prefix: Error prefix for context
    :returns tuple[Optional[str], Optional[list[Exception]]]: The mask
        in octal string form, and never an error
    """
    del e_prefix  # a shell that printed nothing is not a fault

    text = (output or "").strip()
    if not text:
        return None, None

    try:
        return "0%03o" % int(text, 8), None
    except ValueError:
        # A shell asked for the mask and answering symbolically has
        # answered something, but not something this reads
        return None, None


def get_limits_command_requests() -> list[dict[str, Any]]:
    """Build the request that asks a session what it is limited to.

    The effective uid rides with it, because a limit is a fact about
    one session and the answer is worth nothing without knowing whose
    session answered.

    :returns list[dict[str, Any]]: Command requests for run plugin
    """
    from ansible_collections.o0_o.posix.plugins.module_utils.command_spec import (  # noqa: E501
        LIMITS_COMMAND_SPEC,
    )
    from ansible_collections.o0_o.core.plugins.module_utils.evidence_utils import (  # noqa: E501
        EVIDENCE,
    )
    from ansible_collections.o0_o.posix.plugins.module_utils.id_utils import (
        get_effective_uid_command_requests,
    )

    from ansible_collections.o0_o.core.plugins.module_utils import (
        process_command_spec,
    )

    requests = process_command_spec(LIMITS_COMMAND_SPEC)

    # The probe is a script, so argv names the shell that read it back
    # and the shell is not the subject: what was asked is ulimit, a
    # builtin, which is a command a fact may name like any other
    for request in requests:
        request[EVIDENCE] = ["ulimit"]

    return requests + get_effective_uid_command_requests()


def process_limits_command_results(
    cmds_completed: list[dict[str, Any]],
) -> tuple[dict[str, Any], list[Exception]]:
    """Read what a session said it is limited to.

    A probe that answered nothing leaves its field out: a session with
    no ``ulimit`` to ask is not a session with no limits.

    The mask does not come back here.  A umask is a product of the rc
    files a shell read, stable for as long as those files say what
    they say, so it belongs to the shell and the home that produced it
    - which is where the shell probes file it.  A limit is a property
    of one session and is not.

    :param list[dict[str, Any]] cmds_completed: Command results
    :returns tuple[dict[str, Any], list[Exception]]: Tuple of
        (fields, errors)
    """
    processed = process_all_command_results(cmds_completed)

    fields: dict[str, Any] = {}

    limits = (processed.get("ulimit") or {}).get("parsed")
    if limits:
        fields["limits"] = limits

    return fields, []


__all__ = [
    "LIMITS_HARD_MARKER",
    "LIMITS_MAPPING",
    "LIMITS_SOFT_MARKER",
    "LIMITS_UNLIMITED",
    "get_limits_command_requests",
    "process_limits_command_results",
]
