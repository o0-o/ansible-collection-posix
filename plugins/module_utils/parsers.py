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

"""Parser functions for POSIX command specifications.

Parser functions receive (rc, output, e_prefix) and return:
    (parsed_output, errors_or_none)
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Optional

from ansible_collections.o0_o.utils.plugins.module_utils.typeguard_compat import (  # noqa: E501
    typechecked,
)


@typechecked
def command_lookup_parser(
    rc: int,
    output: str,
    e_prefix: str,
    requested_commands: Optional[Iterable[str]] = None,
) -> tuple[dict[str, Optional[str]], Optional[list[Exception]]]:
    """Parse command -v output to determine which commands exist.

    Parses output from running `command -v` on multiple commands.
    Each line of output contains the path to a found command or
    just the command name if it's a shell builtin.

    Example result::

        {
            "cat": "/bin/cat",
            "grep": "/usr/bin/grep",
            "cd": "cd",
            "missing_cmd": None
        }

    Values are the path (or command name for builtins). Commands not
    found are set to None when requested_commands is provided.

    :param int rc: Command return code (unused)
    :param str output: Raw command output (one path per line)
    :param str e_prefix: Error prefix for error messages
    :param Optional[Iterable[str]] requested_commands: Commands that
        were requested; missing ones will be set to None in result
    :returns tuple: (command_to_path_dict, errors_or_none)
    """
    del rc  # unused

    result = {}
    errors = []

    for line in output.strip().splitlines():
        line = line.strip()
        if not line:
            errors.append(
                ValueError(
                    f"{e_prefix}Unexpected empty line in command -v output"
                )
            )
            continue

        if "/" in line:
            # Path - extract command name using basename
            cmd_name = line.rsplit("/", 1)[-1]
            result[cmd_name] = line
        else:
            # Builtin - line is just the command name
            cmd_name = line
            result[cmd_name] = cmd_name

        if requested_commands:
            if cmd_name not in requested_commands:
                errors.append(
                    ValueError(
                        f"{e_prefix}Unexpected command in output: {cmd_name}"
                    )
                )

    if requested_commands:
        for cmd in requested_commands:
            if cmd not in result:
                result[cmd] = None

    return result, errors or None
