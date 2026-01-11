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

"""Command specifications for POSIX compliance detection.

Defines command commands with parsers for getconf compliance checks.
Used with process_command_spec from core to build command requests.
"""

from __future__ import annotations

from ansible_collections.o0_o.posix.plugins.module_utils.compliance_parsers import (  # noqa: E501
    _parse_xsh_version,
    _parse_xcu_version,
    _parse_xopen_support,
    _parse_xopen_versions,
)
from ansible_collections.o0_o.posix.plugins.module_utils.parsers import (
    command_lookup_parser,
)

XCU_REQUIRED_COMMANDS = frozenset(
    {
        # Shell
        "sh",
        # File utilities
        "basename",
        "cat",
        "chmod",
        "chown",
        "cp",
        "dd",
        "df",
        "dirname",
        "du",
        "ln",
        "ls",
        "mkdir",
        "mv",
        "rm",
        "rmdir",
        "stat",
        "touch",
        # Text processing
        "awk",
        "cut",
        "diff",
        "grep",
        "head",
        "paste",
        "sed",
        "sort",
        "tail",
        "tr",
        "uniq",
        "wc",
        # Execution / shell helpers
        "command",
        "env",
        "expr",
        "false",
        "printf",
        "test",
        "[",
        "true",
        "xargs",
        # Identity / environment
        "id",
        "tty",
        "uname",
        # Archiving
        "tar",
    }
)

XSI_REQUIRED_COMMANDS = frozenset(
    {
        "getconf",
        "ipcs",
        "ipcrm",
        "pax",
    }
)

COMPLIANCE_COMMAND_SPEC = {
    "posix": {
        "lookup_xcu_commands": {
            "command": ("command", "-v", *XCU_REQUIRED_COMMANDS),
            "non_error_codes": (0, 1),
            "parser": command_lookup_parser,
            "parser_kwargs": {
                "requested_commands": XCU_REQUIRED_COMMANDS,
            },
        },
        "lookup_xsi_commands": {
            "command": ("command", "-v", *XSI_REQUIRED_COMMANDS),
            "non_error_codes": (0, 1),
            "parser": command_lookup_parser,
            "parser_kwargs": {
                "requested_commands": XSI_REQUIRED_COMMANDS,
            },
        },
        "sh_test": {
            "command": ("sh", "-c", 'x=1; [ "$x" = 1 ] && printf "posix sh"'),
            # TODO: add sh_test_validator
        },
        "xsh_version": {
            "command": ("getconf", "_POSIX_VERSION"),
            "parser": _parse_xsh_version,
        },
        "xcu_version": {
            "command": ("getconf", "_POSIX2_VERSION"),
            "parser": _parse_xcu_version,
        },
        "xopen_support": {
            "command": ("getconf", "_XOPEN_UNIX"),
            "parser": _parse_xopen_support,
        },
        "xopen_version": {
            "command": ("getconf", "_XOPEN_VERSION"),
            "parser": _parse_xopen_versions,
        },
    },
}
