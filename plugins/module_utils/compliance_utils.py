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

"""POSIX/SUS compliance processing utilities.

Constants and processing functions for gathering and processing POSIX,
X/Open, and SUS compliance information.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Optional

from ansible.utils.vars import merge_hash

from ansible_collections.o0_o.utils.plugins.module_utils.typeguard_compat import (  # noqa: E501
    typechecked,
)

from ansible_collections.o0_o.core.plugins.module_utils.command_utils import (
    process_all_command_results,
)


# Standards metadata - used to initialize compliance dict with descriptions
SUS = {
    "name": "Single UNIX Specification",
    "abbreviation": "SUS",
    "description": "Unified UNIX standard combining POSIX with XSI extensions",
}

POSIX = {
    "name": "Portable Operating System Interface",
    "abbreviation": "POSIX",
    "description": "IEEE standard for compatibility between operating systems",
}

XSH = {
    "name": "System Interfaces",
    "abbreviation": "XSH",
    "description": "POSIX System Interfaces and Headers",
}

XCU = {
    "name": "Shell & Utilities",
    "abbreviation": "XCU",
    "description": "POSIX Shell and Utilities",
}

XSI = {
    "name": "X/Open System Interfaces",
    "abbreviation": "XSI",
    "description": "SUS X/Open System Interfaces (UNIX extensions to POSIX)",
}


@typechecked
def _process_getconf_results(
    processed_cmds: dict[str, Any],
    cmd_errors: dict[str, Optional[Sequence[Exception]]],
    commands_result: dict[str, dict[str, Any]],
    compliance: dict[str, Any],
) -> list[Exception]:
    """Process getconf command results and merge into compliance dict.

    Handles xsh_version, xopen_support, xopen_version, and xcu_version
    results. Cross-validates values between different getconf variables.

    :param dict processed_cmds: Parsed command results from parsers
    :param dict cmd_errors: Errors from command parsing
    :param dict commands_result: Original command results for error msgs
    :param dict compliance: Compliance dict to merge results into
    :returns list[Exception]: Errors encountered during processing
    """
    errors = []

    # Process basic getconf results (xsh_version, xopen_support)
    for var in ("xsh_version", "xopen_support"):
        getconf_key = f"getconf_{var}"
        getconf_dict = processed_cmds[getconf_key]
        getconf_errors = cmd_errors[getconf_key]
        if getconf_dict is None:
            cmd_info = commands_result[getconf_key]
            cmd = cmd_info.get("command", var)
            # Command may be tuple (argv) or string
            cmd_str = " ".join(cmd) if isinstance(cmd, tuple) else cmd
            errors.append(
                RuntimeError(
                    f"getconf is present but '{cmd_str}' did not return "
                    f"a valid result"
                )
            )
            if getconf_errors:
                errors.extend(getconf_errors)
        else:
            compliance.update(
                merge_hash(compliance, getconf_dict, recursive=True)
            )

    # Cross-validate _XOPEN_VERSION against other getconf values
    xopen = processed_cmds["xopen_version"]
    if xopen is not None:
        # Check for inconsistencies between _XOPEN_UNIX and _XOPEN_VERSION
        xsi_from_unix = compliance["xsi"].get("supported")
        xsi_from_xopen = xopen["xsi"]["supported"]
        if xsi_from_unix != xsi_from_xopen:
            errors.append(
                ValueError(
                    f"XSI support mismatch: _XOPEN_UNIX indicates "
                    f"{xsi_from_unix} but _XOPEN_VERSION indicates "
                    f"{xsi_from_xopen}"
                )
            )
        xsh_from_posix = compliance["xsh"].get("version")
        xsh_from_xopen = xopen["xsh"]["version"]
        if xsh_from_posix != xsh_from_xopen:
            errors.append(
                ValueError(
                    f"XSH version mismatch: _POSIX_VERSION indicates "
                    f"{xsh_from_posix} but _XOPEN_VERSION indicates "
                    f"{xsh_from_xopen}"
                )
            )
        compliance.update(merge_hash(compliance, xopen, recursive=True))

    # Cross-validate _POSIX2_VERSION against _XOPEN_VERSION
    xcu = processed_cmds["xcu_version"]
    if xcu is not None:
        if compliance.get("xcu"):
            xcu_ver_existing = compliance["xcu"].get("version")
            xcu_ver_new = xcu["xcu"].get("version")
            xcu_sup_existing = compliance["xcu"].get("supported")
            xcu_sup_new = xcu["xcu"].get("supported")
            if xcu_ver_existing != xcu_ver_new:
                errors.append(
                    ValueError(
                        f"XCU version mismatch: _XOPEN_VERSION="
                        f"{xcu_ver_existing} but _POSIX2_VERSION="
                        f"{xcu_ver_new}"
                    )
                )
            if xcu_sup_existing != xcu_sup_new:
                errors.append(
                    ValueError(
                        f"XCU support mismatch: _XOPEN_VERSION="
                        f"{xcu_sup_existing} but _POSIX2_VERSION="
                        f"{xcu_sup_new}"
                    )
                )
        compliance.update(merge_hash(compliance, xcu, recursive=True))

    return errors


@typechecked
def _verify_required_commands(
    compliance: dict[str, Any],
    xcu_cmds: dict[str, Optional[str]],
    xsi_cmds: dict[str, Optional[str]],
) -> tuple[bool, bool, list[Exception]]:
    """Verify required commands are present for claimed support levels.

    Checks that XCU and XSI required commands actually exist on the
    system. Updates compliance dict if commands are missing.

    :param dict compliance: Compliance dict to check/update
    :param dict xcu_cmds: XCU command lookup results (cmd -> path or None)
    :param dict xsi_cmds: XSI command lookup results (cmd -> path or None)
    :returns tuple: (xcu_support, xsi_support, errors)
    """
    errors = []

    # Verify XCU support by checking required commands are present
    xcu_support = compliance["xcu"].get("supported", False)
    missing_xcu_cmds = [cmd for cmd, path in xcu_cmds.items() if path is None]
    if xcu_support and missing_xcu_cmds:
        errors.append(
            ValueError(
                f"getconf reports XCU support but required commands "
                f"are missing: {', '.join(sorted(missing_xcu_cmds))}"
            )
        )
        compliance["xcu"]["supported"] = False
        xcu_support = False

    # Verify XSI support by checking required commands are present
    xsi_support = compliance["xsi"].get("supported", False)
    missing_xsi_cmds = [cmd for cmd, path in xsi_cmds.items() if path is None]
    if xsi_support and missing_xsi_cmds:
        errors.append(
            ValueError(
                f"getconf reports XSI support but required commands "
                f"are missing: {', '.join(sorted(missing_xsi_cmds))}"
            )
        )
        compliance["xsi"]["supported"] = False
        xsi_support = False

    return xcu_support, xsi_support, errors


@typechecked
def _determine_compliance_levels(
    compliance: dict[str, Any],
    xsh_support: bool,
    xcu_support: bool,
    xsi_support: bool,
) -> None:
    """Determine overall POSIX and SUS compliance levels.

    Sets the 'supported' field for posix and sus based on component
    support. Also sets SUS version info if fully compliant.

    :param dict compliance: Compliance dict to update in place
    :param bool xsh_support: Whether XSH is supported
    :param bool xcu_support: Whether XCU is supported
    :param bool xsi_support: Whether XSI is supported
    """
    # POSIX requires both XSH (system interfaces) and XCU (shell/utilities)
    if xsh_support is True and xcu_support is True:
        compliance["posix"]["supported"] = True
    elif xsh_support is False and xcu_support is False:
        compliance["posix"]["supported"] = False
    else:
        compliance["posix"]["supported"] = "partial"

    # SUS requires full POSIX plus XSI extensions
    posix_support = compliance["posix"]["supported"]
    if posix_support is True and xsi_support is True:
        compliance["sus"]["supported"] = True
        # SUS version = XSI Issue - 3 (e.g., Issue 7 = SUSv4)
        xsi_issue = compliance["xsi"].get("version", {}).get("issue")
        if xsi_issue:
            sus_version = int(xsi_issue) - 3
            compliance["sus"]["version"] = {
                "issue": xsi_issue,
                "id": sus_version,
                "pretty": f"v{sus_version}",
            }
    else:
        compliance["sus"]["supported"] = False


@typechecked
def _build_command_inventory(
    xcu_cmds: dict[str, Optional[str]],
    xsi_cmds: dict[str, Optional[str]],
) -> tuple[dict[str, Any], dict[str, Any], list[str]]:
    """Build command inventory from lookup results.

    Categorizes commands into shells (with builtins), paths, and
    missing commands.

    :param dict xcu_cmds: XCU command lookup results
    :param dict xsi_cmds: XSI command lookup results
    :returns tuple: (shells_dict, paths_dict, missing_commands_list)
    """
    commands = {**xcu_cmds, **xsi_cmds}
    missing_commands = []
    shell = {"builtins": []}
    paths = {}

    for cmd, path in commands.items():
        if path is None:
            missing_commands.append(cmd)
        elif cmd == path:
            # Builtins have path == command name
            shell["builtins"].append(cmd)
        else:
            paths[path] = {}

    shells = {
        commands["sh"]: shell,  # Shell path -> builtin info
    }

    return shells, paths, missing_commands


@typechecked
def process_compliance_commands_result(
    commands_result: dict[str, dict[str, Any]],
) -> tuple[dict[str, Any], list[Exception]]:
    """Process compliance command results through their parsers.

    Takes tagged command results from run plugin, calls the appropriate
    parser for each command type, and merges the partial results.

    :param dict[str, dict[str, Any]] commands_result: Dict mapping
        command tags (e.g., "getconf_posix_version") to their results
        containing 'rc' and 'stdout' keys
    :returns tuple[dict[str, Any], list[Exception]]: Tuple of
        (result_dict, errors_list) where result_dict contains
        'compliance', 'shells', 'paths', and 'missing_commands' keys
    """
    # Initialize compliance dict with standard metadata
    compliance = {
        "xsi": XSI.copy(),
        "xsh": XSH.copy(),
        "xcu": XCU.copy(),
        "posix": POSIX.copy(),
        "sus": SUS.copy(),
    }
    errors = []

    # Parse all command results through their registered parsers
    processed_cmds, cmd_errors = process_all_command_results(commands_result)

    # Extract command lookup results (which commands exist on the system)
    xcu_cmds = processed_cmds["lookup_xcu_commands"]
    if cmd_errors["lookup_xcu_commands"]:
        errors.extend(cmd_errors["lookup_xcu_commands"])
    xsi_cmds = processed_cmds["lookup_xsi_commands"]
    if cmd_errors["lookup_xsi_commands"]:
        errors.extend(cmd_errors["lookup_xsi_commands"])

    # Only process getconf results if getconf is available
    if xsi_cmds.get("getconf"):
        getconf_errors = _process_getconf_results(
            processed_cmds, cmd_errors, commands_result, compliance
        )
        errors.extend(getconf_errors)

    # Verify required commands and determine support levels
    xsh_support = compliance["xsh"].get("supported", False)
    xcu_support, xsi_support, verify_errors = _verify_required_commands(
        compliance, xcu_cmds, xsi_cmds
    )
    errors.extend(verify_errors)

    # Determine overall POSIX and SUS compliance
    _determine_compliance_levels(
        compliance, xsh_support, xcu_support, xsi_support
    )

    # Build command inventory
    shells, paths, missing_commands = _build_command_inventory(
        xcu_cmds, xsi_cmds
    )

    result = {
        "compliance": compliance,
        "shells": shells,
        "paths": paths,
        "missing_commands": missing_commands,
    }

    return result, errors
