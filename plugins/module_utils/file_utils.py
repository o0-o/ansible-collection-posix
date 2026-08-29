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

"""Reading a file in the batch every other fact rides.

A fact read from a file is gathered the way every other fact is: a
``cat`` in the one parallel batch, with the raw fallback under it,
never slurp - the collection gathers from hosts that have no Python.
Reading a file through the COMMAND_SPEC pattern is what lets the
reads travel beside the probes rather than in round trips of their
own, so a producer that reads three files spends no more than a
producer that reads none.

``get_file_command_requests`` puts the reads into a batch and
``process_file_command_results`` takes them back out, keyed by the
path each one read.
"""

from __future__ import annotations

from typing import Any

from ansible_collections.o0_o.core.plugins.module_utils import (
    process_all_command_results,
    process_command_spec,
)


def get_file_command_requests(paths: list[str]) -> list[dict[str, Any]]:
    """Build command requests reading each of the named files.

    :param list[str] paths: Paths to read
    :returns list[dict[str, Any]]: Command requests for run plugin
    """
    from ansible_collections.o0_o.posix.plugins.module_utils.command_spec import (  # noqa: E501
        FILE_COMMAND_SPEC,
    )

    return process_command_spec(
        FILE_COMMAND_SPEC,
        cmd_type="file",
        path=list(paths),
    )


def process_file_command_results(
    cmds_completed: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """What the batch learned about each file it read, keyed by path.

    A file that answered carries its bytes under ``parsed``, empty
    string included, because a file that exists and holds nothing is
    not a file that could not be read.  A file that did not answer
    carries ``parsed`` null and says why under ``stderr``, which is
    the caller's to raise on or to pass over: a missing /etc/fstab is
    a fact about the host, and a missing /etc/passwd is a failure,
    and only the caller knows which it asked for.

    :param list[dict[str, Any]] cmds_completed: Command results from
        the run plugin
    :returns dict[str, dict[str, Any]]: The processed result per path
    """
    processed = process_all_command_results(cmds_completed)

    results = processed.get("file")
    if results is None:
        results = []
    elif isinstance(results, dict):
        results = [results]

    return {
        result["args"]["path"]: result
        for result in results
        if result.get("args", {}).get("path")
    }


__all__ = [
    "get_file_command_requests",
    "process_file_command_results",
]
