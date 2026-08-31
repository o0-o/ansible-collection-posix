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

"""What the kernel says its own tunables are.

``sysctl`` is not POSIX and its keys are not portable: what a key is
called, what its values mean and which of them exist differ by kernel
and by version, so nothing here parses a value or claims to know what
one signifies.  The listing mechanism is what generalizes, and this is
a parser for the three shapes the listing comes in.

Three separators, one per implementation.  Linux procps prints
``key = value``, FreeBSD and macOS print ``key: value``, and OpenBSD
prints ``key=value``.  A key is a run of characters with no whitespace
and neither separator in it, which is what keeps a value from faking
one: macOS answers ``kern.version`` with a string that has ``: `` in
the middle of it, and Linux answers ``dev.cdrom.info`` with a line
reading ``drive name:``, so a parser that split on the first separator
it found would cut both in the wrong place.

Two implementations spell a multiline value two different ways, and
both mean the kernel holds a string with a newline in it.

The BSDs print the first line after the separator and the rest as
lines of their own, indented, the way ``kern.version`` carries its
build path.  A line that does not parse as a new key is therefore the
continuation of the value before it - a recognized form rather than a
fallback, and never an error.

Linux prints the key again on every line, which is what ``sysctl -a``
and ``sysctl dev.cdrom.info`` both do on a running host.  So a key
seen twice is not a key overwritten: its lines are joined back into
the one value the kernel holds.

Either way the answer is one string with the newlines it was printed
with.  Output whose very first line names no key at all is not sysctl
output, and that is the one thing here that is an error.
"""

from __future__ import annotations

import re

from typing import Any, Optional

from ansible_collections.o0_o.core.plugins.module_utils import (
    process_all_command_results,
    process_command_spec,
)

# One line of a listing, in whichever of the three forms the host
# prints.  The key admits neither separator nor whitespace, so the
# match cannot start inside a value; the single optional space after
# the separator is the printing convention rather than the value.
SYSCTL_LINE = re.compile(r"^(?P<key>[^\s=:]+)[ \t]*[=:][ \t]?(?P<value>.*)$")

# What a host answers when it has no such key.  Linux exits 1 and says
# it cannot stat the /proc path; the BSDs exit 1 and name the level.
# Either way the key is absent rather than the command broken, so the
# status rides back as an answer for the caller to read.  The status
# for no sysctl at all rides back with them, because a host without
# the tool is a different claim from a host without the key, and the
# caller can only tell them apart if both arrive.
SYSCTL_RCS = [0, 1, 2, 126, 127, 255]

# What a shell exits with when the tool is not there to run, or is
# there and will not run.  A POSIX host need not have sysctl at all.
SYSCTL_MISSING_RCS = (126, 127)

# What this module is called, which is what an answer names as having
# composed it
FQCN = "o0_o.posix.sysctl"


def _parse_sysctl(
    rc: int,
    output: str,
    e_prefix: str,
) -> tuple[Optional[dict[str, str]], Optional[list[Exception]]]:
    """Canonical COMMAND_SPEC parser for a sysctl listing.

    Answers with a value per key, verbatim, in the order the host
    printed them.  Nothing is typed: a key's meaning is the kernel's
    and a number here may be a count, a bitmask, a flag or a tuple of
    all three depending on which kernel answered.

    The exit status is not the test of whether there is anything to
    read.  A listing exits non-zero on a host holding keys it will not
    read, having printed every key it would, so what was printed is
    parsed whatever the status; and a refusal prints nothing, which is
    an answer of None rather than a fault.

    :param int rc: The exit status, which the caller reads to tell a
        refused key from an answered one
    :param str output: Raw stdout of the listing
    :param str e_prefix: Error prefix for context
    :returns tuple[Optional[dict[str, str]], Optional[list[Exception]]]:
        The values keyed by key, and an error where the output names no
        key at all
    """
    del rc  # what was printed is parsed whatever the status

    values: dict[str, str] = {}
    named: Optional[str] = None

    for line in (output or "").splitlines():
        if not line:
            continue

        found = SYSCTL_LINE.match(line)

        if found is None:
            if named is None:
                return None, [
                    ValueError(
                        f"{e_prefix}sysctl printed a line naming no key:"
                        f" {line!r}"
                    )
                ]

            # The BSD spelling of a newline: the rest of the value the
            # key before it opened, indented and printed on its own
            values[named] = f"{values[named]}\n{line}"
            continue

        key = found.group("key")
        value = found.group("value")

        # The Linux spelling of the same thing: the key again, once per
        # line of the one value the kernel holds
        values[key] = (
            f"{values[key]}\n{value}" if key in values else value
        )
        named = key

    return (values or None), None


def get_sysctl_listing_requests() -> list[dict[str, Any]]:
    """Build the request that asks a host for every key it prints.

    :returns list[dict[str, Any]]: Command requests for run plugin
    """
    from ansible_collections.o0_o.posix.plugins.module_utils.command_spec import (  # noqa: E501
        SYSCTL_COMMAND_SPEC,
    )

    return process_command_spec(
        SYSCTL_COMMAND_SPEC, cmd_type="sysctl_listing"
    )


def get_sysctl_key_requests(keys: list[str]) -> list[dict[str, Any]]:
    """Build one request per key a caller asked about.

    One key per invocation rather than one invocation naming many,
    because the exit status is the answer: a host asked about five
    keys and refusing one says so once for the whole command, and
    which of the five it meant is then a guess.  Asked one at a time
    the refusal belongs to the key that earned it, and the batch still
    costs one round trip.

    :param list[str] keys: The keys to ask about
    :returns list[dict[str, Any]]: Command requests for run plugin
    """
    from ansible_collections.o0_o.posix.plugins.module_utils.command_spec import (  # noqa: E501
        SYSCTL_COMMAND_SPEC,
    )

    return process_command_spec(
        SYSCTL_COMMAND_SPEC,
        cmd_type="sysctl_key",
        key=list(keys),
    )


def get_sysctl_assignment_requests(
    values: dict[str, str],
) -> list[dict[str, Any]]:
    """Build one request per key a caller is setting.

    The assignment is written plainly, as ``sysctl key=value``, which
    is the one spelling every implementation takes.  ``-w`` is the
    procps and FreeBSD spelling of it and OpenBSD has no such flag.

    :param dict[str, str] values: The value to set, keyed by key
    :returns list[dict[str, Any]]: Command requests for run plugin
    """
    from ansible_collections.o0_o.posix.plugins.module_utils.command_spec import (  # noqa: E501
        SYSCTL_COMMAND_SPEC,
    )

    return process_command_spec(
        SYSCTL_COMMAND_SPEC,
        cmd_type="sysctl_assign",
        assignment=[f"{key}={values[key]}" for key in sorted(values)],
    )


def process_sysctl_command_results(
    cmds_completed: list[dict[str, Any]],
    keys: Optional[list[str]] = None,
) -> tuple[dict[str, Optional[str]], list[Exception]]:
    """Read what a host answered about its own tunables.

    A key the host refused is answered null rather than left out.  The
    caller named it, so the answer is about that key, and null is this
    collection's word for asked about and not there - the same thing a
    path store means by it.

    A key nobody asked about is not here at all, which is the other
    half of the same contract.

    :param list[dict[str, Any]] cmds_completed: Command results
    :param Optional[list[str]] keys: The keys that were asked about,
        where a caller named them, so a refusal can be filed under the
        key that earned it
    :returns tuple[dict[str, Optional[str]], list[Exception]]: The
        values keyed by key, and the errors reading them raised
    """
    processed = process_all_command_results(cmds_completed)

    values: dict[str, Optional[str]] = {}
    errors: list[Exception] = []

    for cmd_type in ("sysctl_listing", "sysctl_key"):
        results = processed.get(cmd_type)
        if results is None:
            continue
        if isinstance(results, dict):
            results = [results]

        for result in results:
            if not isinstance(result, dict):
                continue

            parsed = result.get("parsed")
            if isinstance(parsed, dict):
                values.update(parsed)

            for error in result.get("errors") or []:
                errors.append(error)

    # Every key the caller named gets an answer, and a key the host
    # would not answer for gets the one that says it is not there
    for key in keys or []:
        values.setdefault(key, None)

    return values, errors


__all__ = [
    "FQCN",
    "SYSCTL_LINE",
    "SYSCTL_MISSING_RCS",
    "SYSCTL_RCS",
    "get_sysctl_assignment_requests",
    "get_sysctl_key_requests",
    "get_sysctl_listing_requests",
    "process_sysctl_command_results",
]
