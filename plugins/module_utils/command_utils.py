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

"""Command utilities for POSIX action plugins.

Standalone functions for command formatting, argument sanitization,
interpreter detection, and shell quoting. These functions are designed
to be used independently of ActionBase classes.
"""

from __future__ import annotations

import shlex
from typing import Any, Optional, Union

from ansible.module_utils.common.text.converters import to_native


def format_command(cmd: Union[str, list[str]]) -> str:
    """Convert a command to a shell-safe string.

    Handles both string and list inputs, properly quoting list
    elements for shell execution. List elements are automatically
    converted to native strings to handle non-string types like
    integers or Path objects.

    :param cmd: Command as string or list of arguments
    :returns str: Shell-safe command string
    """
    if isinstance(cmd, str):
        # Validate syntax and normalize quoting by tokenizing
        # and re-joining
        cmd = shlex.split(cmd)
    else:
        # Convert all list elements to native strings
        cmd = [
            to_native(
                arg, errors="surrogate_or_strict", nonstring="simplerepr"
            )
            for arg in cmd
        ]
    try:
        # Use shlex.join() if available (Python 3.8+)
        return shlex.join(cmd)
    except AttributeError:
        # Python < 3.8 fallback
        return " ".join(shlex.quote(str(arg)) for arg in cmd)


def is_interpreter_missing(
    result: dict[str, Any],
    display: Optional[Any] = None,
) -> bool:
    """Check if failure was likely caused by a missing Python interpreter.

    :param dict[str, Any] result: A result dict from _execute_module or
        fallback command
    :param Optional[Any] display: Ansible Display object for verbose
        output. If provided, logs detection via display.vv()
    :returns bool: True if failure likely due to missing Python,
        else False
    """
    if not isinstance(result, dict):
        return False

    if result.get("rc") != 127:
        return False

    msg = result.get("msg", "")
    stderr = result.get("stderr", "")
    module_stderr = result.get("module_stderr", "")
    module_stdout = result.get("module_stdout", "")

    # Check all text fields for interpreter errors
    text_to_check = " ".join(
        [
            str(msg) if isinstance(msg, str) else "",
            str(stderr) if isinstance(stderr, str) else "",
            str(module_stderr) if isinstance(module_stderr, str) else "",
            str(module_stdout) if isinstance(module_stdout, str) else "",
        ]
    ).lower()

    # Ansible's standard error message
    canary_str = (
        "The module failed to execute correctly, you probably need to set "
        "the interpreter"
    )

    # Check for the standard canary or signs of missing Python
    if canary_str.lower() in text_to_check:
        if display is not None:
            display.vv("Python interpreter not found")
        return True

    # Check for shell error indicating Python not found
    # Examples: "/usr/bin/python3: not found", "python: not found"
    python_patterns = [
        "python: not found",
        "python2: not found",
        "python3: not found",
    ]

    if any(pattern in text_to_check for pattern in python_patterns):
        if display is not None:
            display.vv("Python interpreter not found (shell error)")
        return True

    return False


def sanitize_args(args: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of the argument dictionary with all None values removed.

    This is useful when passing arguments to Ansible modules that
    enforce mutually exclusive parameters or expect missing values
    to be omitted rather than explicitly set to null/None.

    :param dict[str, Any] args: Dictionary of module arguments to sanitize
    :returns dict[str, Any]: A new dictionary with all None values removed
    """
    return {k: v for k, v in args.items() if v is not None}


def quote(s: str, shell: Optional[Any] = None) -> str:
    """Quote a string for safe use in shell commands.

    Uses the provided shell's quoting logic if available (e.g., for
    non-POSIX shells), falling back to Python's ``shlex.quote()`` for
    standard POSIX-compatible escaping.

    :param str s: The string to quote
    :param Optional[Any] shell: Shell plugin instance with quote() method.
        If None, uses shlex.quote()
    :returns str: The safely quoted string
    """
    if shell is not None:
        quote_fn = getattr(shell, "quote", None)
        if quote_fn is not None:
            return quote_fn(s)
    return shlex.quote(s)
