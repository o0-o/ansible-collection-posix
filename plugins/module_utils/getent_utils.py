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

"""The host's own resolved view of its users and groups.

``getent`` asks the name service switch what a host's users and
groups actually are, which on a host that resolves names anywhere but
its flat files is more than those files say.  The answer overlays the
files parse in ``compose_users_groups``; this module is how the answer
is asked for and how a getent worth believing is told from one that is
not.

Something answering to the name ``getent`` is not necessarily the
program: zsh's ``compaudit`` defines a shell function of that name on
hosts that have no such binary, and that function greps the flat files
with no idea the name service switch exists.  A shim's answer is the
files parse wearing a second name, and publishing it as the resolved
view would claim a resolution that never happened.

So legitimacy is established behaviorally, from what the candidate
does rather than what it is called, and the discriminator is the
enumeration itself: asked for a whole database with no key, the real
program prints it and exits 0, and the shim - which has only a key to
grep for and no key to grep with - prints nothing and exits 1.  The
probe is therefore free, because it is the same command the gather
needs anyway.  ``getent -V`` is no help and is not asked: it is a
glibc marker, not a getent one, and musl's getent rejects it exactly
as the shim does.

Nothing here can prove the answer came through the name service
switch rather than off the disk, and on a files-only host the two are
the same bytes.  ``sources`` claims only what was asked and answered:
that getent said so.
"""

from __future__ import annotations

from typing import Any, Optional

from ansible_collections.o0_o.core.plugins.module_utils import (
    process_all_command_results,
    process_command_spec,
)

from ansible_collections.o0_o.posix.plugins.module_utils.group_utils import (
    group_info,
)
from ansible_collections.o0_o.posix.plugins.module_utils.passwd_utils import (
    passwd_info,
)

# The databases the canonical user facts are composed from
GETENT_DATABASES = ("passwd", "group")

# Every return code the probe reads as an answer rather than a fault,
# so that the parser is the one deciding what the candidate is.  0 is
# an enumeration; 1 is the shim's failed grep and both libcs' refusal
# of an argument they do not know; 2 is the real family's word for a
# key that is not there and grep's for a file that is not; 126 and 127
# are the shell's for a getent that cannot be run and one that is not
# installed.  Absence and illegitimacy are the same answer here, and
# neither is an error.
GETENT_RCS = [0, 1, 2, 126, 127]

# How each database's enumeration is read back into entries
_DATABASE_PARSERS = {"passwd": passwd_info, "group": group_info}


def _parse_getent(
    rc: int,
    output: str,
    e_prefix: str,
    database: str = "passwd",
) -> tuple[Optional[str], Optional[list[Exception]]]:
    """Canonical COMMAND_SPEC parser and legitimacy probe for getent.

    Answers with the enumeration verbatim where the candidate proved
    to be a getent, and with None where it did not, so that a host
    with no getent, a host whose getent is a grep shim, and a host
    whose getent answered nothing all reach the composition the same
    way: with nothing to overlay, and files-only gathering unchanged.

    Legitimacy is rc 0 and an enumeration that parses as at least one
    entry.  The rc alone would take a shim at its word on any day it
    happened to exit 0, and output alone would take a usage message
    for a database, so both are required.  What the parse yields is
    thrown away: the bytes are the answer, and the composition is
    where they mean something.

    A candidate that failed the probe is absent as far as the caller
    is concerned, and absence is not an error, so no error is raised
    and none is returned.

    :param int rc: The candidate's exit status
    :param str output: Raw stdout of the enumeration
    :param str e_prefix: Error prefix for context
    :param str database: The database enumerated, naming the parse
        its output has to satisfy
    :returns tuple[Optional[str], Optional[list[Exception]]]: The
        enumeration where the candidate is a getent, None where it is
        not, and never an error
    """
    del e_prefix  # absence is not an error, so nothing is prefixed

    if rc != 0 or not (output or "").strip():
        return None, None

    parse = _DATABASE_PARSERS[database]

    try:
        entries = parse(output, key="id")
    except Exception:
        return None, None

    if not entries:
        return None, None

    return output, None


def get_getent_command_requests() -> list[dict[str, Any]]:
    """Build command requests for the host's resolved user view.

    One enumeration per database, which is both the probe and the
    answer: a host with a real getent has already given the gather
    what it came for by the time the fingerprint is read.

    :returns list[dict[str, Any]]: Command requests for run plugin
    """
    from ansible_collections.o0_o.posix.plugins.module_utils.command_spec import (  # noqa: E501
        GETENT_COMMAND_SPEC,
    )

    return process_command_spec(GETENT_COMMAND_SPEC)


def process_getent_command_results(
    cmds_completed: list[dict[str, Any]],
) -> dict[str, Optional[str]]:
    """Read the resolved view back out of a batch's results.

    Answers with an entry per database, holding the enumeration where
    one was had and None where none was, so a caller composing with
    this never has to ask whether the host has getent - it asks what
    getent said, and None is a complete answer.

    :param list[dict[str, Any]] cmds_completed: Command results
    :returns dict[str, Optional[str]]: The enumeration per database,
        None where the host has no getent worth believing
    """
    processed = process_all_command_results(cmds_completed)

    resolved: dict[str, Optional[str]] = {}
    for database in GETENT_DATABASES:
        result = processed.get(f"getent_{database}")
        if not isinstance(result, dict):
            resolved[database] = None
            continue
        parsed = result.get("parsed")
        resolved[database] = parsed if isinstance(parsed, str) else None

    return resolved


__all__ = [
    "GETENT_DATABASES",
    "GETENT_RCS",
    "get_getent_command_requests",
    "process_getent_command_results",
]
