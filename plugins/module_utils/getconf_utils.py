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

"""What the host says its own configuration is.

``getconf`` is POSIX's interface to its own configuration variables,
and this module asks it two classes of them.  The ``sysconf`` limits,
the ``confstr`` strings and the standard versions describe the host,
and are asked once.  The ``pathconf`` class takes a pathname and
describes the filesystem behind it, so it is asked once at each
mountpoint and lands on the mount rather than on the host: what the
longest name is and how big a file may get are answers a host does
not have, only its filesystems do.

One variable per invocation, because that is the only interface POSIX
defines.  ``getconf -a`` would answer the whole set in one command, but
it is an extension, and the three implementations that have it print
three different formats - ``NAME: value``, ``NAME = value`` and
``NAME`` padded to a column - so a parser for it would be a parser for
whichever host it was written on.  The sweep costs one command per
variable and rides the batch a gather was already sending.

Absence is the normal answer, not a fault.  No two ``getconf``
implementations know the same variables: musl has no ``HOST_NAME_MAX``,
glibc has no ``_POSIX2_VERSION``, macOS has no ``CS_PATH``, and Linux
knows ``NPROCESSORS_ONLN`` only under its leading underscore.  Each
refuses in its own dialect and with its own exit status - 1 on musl, 2
on glibc, 64 on macOS - so the sweep reads every plausible status as an
answer and lets the parser decide.  A variable the host does not know
is left out of the fact rather than published as a null, because a
null here means something else.

What it means is ``undefined``: the answer a host gives for a variable
it has and does not limit.  That is a real answer and it keeps its
key, valued null, so a caller can tell a limit the host does not
impose from a variable the host has never heard of by asking whether
the key is there at all.
"""

from __future__ import annotations

from typing import Any, Optional, Union

from ansible_collections.o0_o.core.plugins.module_utils import (
    process_all_command_results,
    process_command_spec,
)

from ansible_collections.o0_o.posix.plugins.module_utils.evidence_utils import (  # noqa: E501
    commands_run,
    compose_evidence,
)

# The variables the sweep asks for: the sysconf limits, the confstr
# strings and the standard versions, which is the whole host-invariant
# class.  Both spellings of the ones that have two are asked, because
# which spelling a host answers to is the host's business - macOS
# answers ``NPROCESSORS_ONLN`` and both libcs answer only
# ``_NPROCESSORS_ONLN`` - and asking both is how the fact is the
# host's answer rather than the collection's guess about it.
GETCONF_SYSCONF_VARIABLES = (
    "ARG_MAX",
    "ATEXIT_MAX",
    "BC_BASE_MAX",
    "BC_DIM_MAX",
    "BC_SCALE_MAX",
    "BC_STRING_MAX",
    "CHILD_MAX",
    "CLK_TCK",
    "COLL_WEIGHTS_MAX",
    "CS_PATH",
    "EXPR_NEST_MAX",
    "HOST_NAME_MAX",
    "IOV_MAX",
    "LINE_MAX",
    "LOGIN_NAME_MAX",
    "NGROUPS_MAX",
    "NPROCESSORS_CONF",
    "NPROCESSORS_ONLN",
    "OPEN_MAX",
    "PAGESIZE",
    "PAGE_SIZE",
    "PATH",
    "RE_DUP_MAX",
    "STREAM_MAX",
    "SYMLOOP_MAX",
    "TTY_NAME_MAX",
    "TZNAME_MAX",
    "_NPROCESSORS_CONF",
    "_NPROCESSORS_ONLN",
    "_POSIX2_VERSION",
    "_POSIX_VERSION",
    "_XOPEN_VERSION",
)

# The variables a filesystem answers, asked at a mountpoint.  The
# terminal members of the pathconf class - MAX_CANON, MAX_INPUT,
# _POSIX_VDISABLE - are not asked: they describe a tty and say nothing
# about a filesystem, and macOS refuses them for a directory rather
# than answering.
GETCONF_PATHCONF_VARIABLES = (
    "FILESIZEBITS",
    "LINK_MAX",
    "NAME_MAX",
    "PATH_MAX",
    "PIPE_BUF",
    "POSIX_ALLOC_SIZE_MIN",
    "SYMLINK_MAX",
    "_POSIX_CHOWN_RESTRICTED",
    "_POSIX_NO_TRUNC",
)

# Every exit status the sweep reads as an answer rather than a fault.
# 0 is a value; 1 is musl's word for a variable it does not know and 2
# is glibc's, which it also uses for the usage message it prints
# instead of an error for a name it half recognizes; 64 is macOS's
# EX_USAGE for the same refusal and 71 its EX_OSERR for a pathconf
# variable a filesystem will not answer; 126 and 127 are the shell's
# for a getconf that cannot be run and one that is not installed.
# Every one of them means the same thing to the fact - no value - and
# none of them is an error.
GETCONF_RCS = [0, 1, 2, 64, 71, 126, 127]

# What a host prints for a variable it has and does not limit
GETCONF_UNDEFINED = "undefined"


def _parse_getconf(
    rc: int,
    output: str,
    e_prefix: str,
) -> tuple[Optional[Union[int, str]], Optional[list[Exception]]]:
    """Canonical COMMAND_SPEC parser for one ``getconf`` answer.

    Answers with an int where the host printed a number, a string
    where it printed anything else, and None where it printed nothing
    the fact can carry - which is a refusal, an empty answer, or the
    literal ``undefined``.  The caller tells the last of those from
    the first two by the exit status, which travels with the result.

    Numbers are ints because they are counts and sizes and every
    consumer of them does arithmetic; ``getconf PATH`` and its kind
    stay strings because they are paths.  Nothing is coerced beyond
    that: a host that answers ``-1`` for an option it does not support
    has said ``-1``, and the fact says so.

    A variable the host does not know is not an error, so none is
    raised and none is returned.

    :param int rc: The exit status ``getconf`` answered with
    :param str output: Raw stdout of the invocation
    :param str e_prefix: Error prefix for context
    :returns tuple[Optional[Union[int, str]], Optional[list[Exception]]]:
        The value the host named, and never an error
    """
    del e_prefix  # a variable the host does not have is not a fault

    if rc != 0:
        return None, None

    text = (output or "").strip()
    if not text or text == GETCONF_UNDEFINED:
        return None, None

    try:
        return int(text), None
    except ValueError:
        return text, None


def get_getconf_command_requests(
    variables: Optional[tuple[str, ...]] = None,
) -> list[dict[str, Any]]:
    """Build command requests for the host's configuration sweep.

    One request per variable, which is what POSIX's interface allows
    and what the list-expansion mechanism was built for.

    :param Optional[tuple[str, ...]] variables: The variables to ask
        for, defaulting to the whole host-invariant class
    :returns list[dict[str, Any]]: Command requests for run plugin
    """
    from ansible_collections.o0_o.posix.plugins.module_utils.command_spec import (  # noqa: E501
        GETCONF_COMMAND_SPEC,
    )

    return process_command_spec(
        GETCONF_COMMAND_SPEC,
        cmd_type="getconf_sysconf",
        var=list(variables or GETCONF_SYSCONF_VARIABLES),
    )


def _answered(result: Any) -> bool:
    """Say whether a result is a value rather than a refusal.

    A refusal parses to None and so does ``undefined``, so the two are
    told apart here, where the exit status is still in reach, rather
    than in the parser, where only the value is.

    :param Any result: One processed result of a sweep
    :returns bool: True where the host named something
    """
    return (
        isinstance(result, dict)
        and result.get("rc") == 0
        and bool((result.get("stdout") or "").strip())
    )


def compose_getconf(results: list[dict[str, Any]]) -> dict[str, Any]:
    """Compose the configuration fact from the sweep's answers.

    Keyed by the variable asked for, which is the only name the host
    and the fact agree on.  A variable the host refused is left out; a
    variable it answered ``undefined`` for is present and null.

    :param list[dict[str, Any]] results: Processed results of the
        sweep, each carrying the exit status and the variable asked
    :returns dict[str, Any]: The values the host named, keyed by
        variable
    """
    config: dict[str, Any] = {}

    for result in results:
        if not _answered(result):
            continue
        variable = (result.get("args") or {}).get("var")
        if variable:
            config[variable] = result.get("parsed")

    return config


def compose_pathconf(
    results: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Compose each path's configuration from the sweep's answers.

    Keyed by the path probed and then by the variable asked for.  A
    path whose filesystem answered nothing is left out entirely rather
    than carried as an empty mapping, so a caller joining this to the
    mounts attaches a configuration only where there is one.

    :param list[dict[str, Any]] results: Processed results of the
        sweep, each carrying the exit status, the variable asked and
        the path it was asked at
    :returns dict[str, dict[str, Any]]: The values each filesystem
        named, keyed by path and then by variable
    """
    config: dict[str, dict[str, Any]] = {}

    for result in results:
        if not _answered(result):
            continue
        args = result.get("args") or {}
        path = args.get("path")
        variable = args.get("var")
        if path and variable:
            config.setdefault(path, {})[variable] = result.get("parsed")

    return config


def get_pathconf_command_requests(
    paths: list[str],
    variables: Optional[tuple[str, ...]] = None,
) -> list[dict[str, Any]]:
    """Build command requests for each path's configuration.

    One request per variable per path, which is the cost of the only
    interface POSIX defines and the reason these ride a batch rather
    than going one at a time.  The path is an argument rather than
    part of a command line, so a mountpoint with a space in it is a
    mountpoint with a space in it.

    :param list[str] paths: The paths to probe at
    :param Optional[tuple[str, ...]] variables: The variables to ask
        for, defaulting to the whole filesystem class
    :returns list[dict[str, Any]]: Command requests for run plugin
    """
    from ansible_collections.o0_o.posix.plugins.module_utils.command_spec import (  # noqa: E501
        GETCONF_COMMAND_SPEC,
    )

    if not paths:
        return []

    return process_command_spec(
        GETCONF_COMMAND_SPEC,
        cmd_type="getconf_pathconf",
        var=list(variables or GETCONF_PATHCONF_VARIABLES),
        path=list(paths),
    )


def process_pathconf_command_results(
    cmds_completed: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Read each path's configuration out of a batch's results.

    :param list[dict[str, Any]] cmds_completed: Command results
    :returns dict[str, dict[str, Any]]: The values each filesystem
        named, keyed by path and then by variable
    """
    processed = process_all_command_results(cmds_completed)

    results = processed.get("getconf_pathconf")
    if results is None:
        return {}
    if isinstance(results, dict):
        results = [results]

    return compose_pathconf(results)


def process_getconf_command_results(
    cmds_completed: list[dict[str, Any]],
) -> tuple[dict[str, Any], list[Exception]]:
    """Read the configuration fact back out of a batch's results.

    A host that answered nothing at all - no ``getconf``, or one that
    refused every variable - leaves the namespace unpublished rather
    than published empty, because an empty answer and no answer are
    not the same claim.

    :param list[dict[str, Any]] cmds_completed: Command results
    :returns tuple[dict[str, Any], list[Exception]]: Tuple of
        (facts_dict, errors) where facts_dict has the o0_os namespace
        key
    """
    processed = process_all_command_results(cmds_completed)

    results = processed.get("getconf_sysconf")
    if results is None:
        return {}, []
    if isinstance(results, dict):
        results = [results]

    config = compose_getconf(results)
    if not config:
        return {}, []

    # The namespace names what was consulted, and nothing more: these
    # variables are the fact here rather than evidence for one, and a
    # fact is not evidence for itself.
    return {
        "o0_os": {
            "config": config,
            "evidence": compose_evidence(
                commands=commands_run(cmds_completed, "getconf_sysconf")
            ),
        }
    }, []


__all__ = [
    "GETCONF_PATHCONF_VARIABLES",
    "GETCONF_RCS",
    "GETCONF_SYSCONF_VARIABLES",
    "GETCONF_UNDEFINED",
    "compose_getconf",
    "compose_pathconf",
    "get_getconf_command_requests",
    "get_pathconf_command_requests",
    "process_getconf_command_results",
    "process_pathconf_command_results",
]
