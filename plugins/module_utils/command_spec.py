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

"""Command specifications for POSIX operations.

Defines generic command specs and module-specific command specs.
Used with process_command_spec from core to build command requests.
"""

from __future__ import annotations

from ansible_collections.o0_o.core.plugins.module_utils.parsers import (
    strip_only,
)

from ansible_collections.o0_o.posix.plugins.module_utils.compliance_parsers import (  # noqa: E501
    _parse_posix_version,
    _parse_sh_test,
    _parse_xopen_support,
    _parse_xopen_version,
)
from ansible_collections.o0_o.posix.plugins.module_utils.uname_utils import (
    _parse_uname,
)

# Generic reusable command specifications
COMMAND_SPEC = {
    "posix": {
        "lookup_command": {
            # NOTE: dash only outputs the first arg to `command -v`.
            # Use cmd as a list to generate one request per command.
            "command": ("command", "-v", "{cmd}"),
            "parser": strip_only,
        },
    },
}

# Uname command spec
UNAME_COMMAND_SPEC = {
    "posix": {
        "uname": {
            "command": ("uname", "-a"),
            "parser": _parse_uname,
        },
    },
}

# Compliance-specific command specs for getconf and shell tests
COMPLIANCE_COMMAND_SPEC = {
    "posix": {
        "sh_test": {
            "command": ("sh", "-c", 'x=1; [ "$x" = 1 ] && printf "posix sh"'),
            "parser": _parse_sh_test,
        },
        "xsh_version": {
            "command": ("getconf", "_POSIX_VERSION"),
            "parser": _parse_posix_version,
        },
        "xcu_version": {
            "command": ("getconf", "_POSIX2_VERSION"),
            "parser": _parse_posix_version,
        },
        "xsi_support": {
            "command": ("getconf", "_XOPEN_UNIX"),
            "parser": _parse_xopen_support,
        },
        "xsi_version": {
            "command": ("getconf", "_XOPEN_VERSION"),
            "parser": _parse_xopen_version,
        },
    },
}
