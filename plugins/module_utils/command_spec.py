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

"""Command specifications for POSIX command execution.

This module defines command templates organized by implementation type.
Each specification includes a template and optional parser/validator.

Extends the core COMMAND_SPEC with POSIX-specific commands.

Example usage::

    # Get command requests for getconf _POSIX_VERSION
    requests = process_command_spec(COMMAND_SPEC, "getconf_posix_version")
    # Returns list of command request dicts with formatted templates
"""

from __future__ import annotations

from typing import Any, Dict

from ansible_collections.o0_o.core.plugins.module_utils.command_spec import (
    COMMAND_SPEC as CORE_COMMAND_SPEC,
)
from ansible_collections.o0_o.posix.plugins.module_utils.parsers import (
    parse_posix_version,
    parse_posix2_version,
    parse_xopen_unix,
    parse_xopen_version,
    parse_xopen_xcu_version,
)

COMMAND_SPEC: Dict[str, Dict[str, Any]] = {
    **CORE_COMMAND_SPEC,
    "posix": {
        "getconf_posix_version": {
            "template": ("getconf", "_POSIX_VERSION"),
            "parser": parse_posix_version,
        },
        "getconf_posix2_version": {
            "template": ("getconf", "_POSIX2_VERSION"),
            "parser": parse_posix2_version,
        },
        "getconf_xopen_unix": {
            "template": ("getconf", "_XOPEN_UNIX"),
            "parser": parse_xopen_unix,
        },
        "getconf_xopen_version": {
            "template": ("getconf", "_XOPEN_VERSION"),
            "parser": parse_xopen_version,
        },
        "getconf_xopen_xcu_version": {
            "template": ("getconf", "_XOPEN_XCU_VERSION"),
            "parser": parse_xopen_xcu_version,
        },
    },
}
