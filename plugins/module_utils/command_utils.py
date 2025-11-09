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

from __future__ import annotations

import shlex
from typing import List, Union

__all__ = ["format_command", "format_command_list"]


def format_command(cmd: Union[str, List[str]]) -> str:
    """
    Convert a command to a shell-safe string.

    Handles both string and list inputs, properly quoting list elements
    for shell execution.

    :param cmd: Command as string or list of arguments
    :returns str: Shell-safe command string

    Examples:
        >>> format_command("ls -la")
        'ls -la'
        >>> format_command(["ls", "-la", "/path with spaces"])
        "ls -la '/path with spaces'"
    """
    if isinstance(cmd, str):
        return cmd

    # Use shlex.join() if available (Python 3.8+), fallback to manual quoting
    try:
        return shlex.join(cmd)
    except AttributeError:
        # Python < 3.8 fallback
        return " ".join(shlex.quote(str(arg)) for arg in cmd)


def format_command_list(commands: List[Union[str, List[str]]]) -> List[str]:
    """
    Convert a list of commands (each string or list) to shell-safe strings.

    :param commands: List of commands (each as string or list)
    :returns List[str]: List of shell-safe command strings

    Example:
        >>> format_command_list([
        ...     ["cat", "/path with spaces"],
        ...     "ls -la",
        ... ])
        ["cat '/path with spaces'", 'ls -la']
    """
    return [format_command(cmd) for cmd in commands]
