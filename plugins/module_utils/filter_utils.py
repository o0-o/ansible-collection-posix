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

"""Filter processing utilities."""

from __future__ import annotations

from typing import Any, Callable, Dict, Union


def process_registered_result(
    config: Dict[str, Any], parser: Callable[[Union[str, list]], Any]
) -> Any:
    """Process registered result dict with automatic base64 detection.

    Handles dict input from registered results (command/slurp modules):
    - Extracts content from 'stdout' or 'content' keys
    - Automatically detects and decodes base64 for 'content' key
    - Falls back to base64 decode on parse errors

    :param config: Dict with registered result from command or slurp
    :param parser: Function to parse the extracted content
    :returns: Result from parser function
    :raises ValueError: If dict doesn't have required keys or fails
    """
    import base64

    if "stdout" in config:
        content = config["stdout"]
        # stdout is never base64 encoded
        return parser(content)
    elif "content" in config:
        content = config["content"]
        # content from slurp is usually base64 encoded
        # Try parsing as-is first (in case it's not encoded)
        try:
            return parser(content)
        except (ValueError, Exception) as e:
            # Try base64 decode and parse
            try:
                decoded = base64.b64decode(content).decode("utf-8")
                return parser(decoded)
            except Exception:
                # Not base64 or decode failed, raise original error
                raise e
    else:
        raise ValueError(
            "Dict input must have 'stdout' or 'content' key for parsing"
        )
