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

from typing import Any

from ansible_collections.o0_o.utils.plugins.module_utils import (
    merge_hash,
    typechecked,
)

from ansible_collections.o0_o.core.plugins.module_utils import (
    process_all_command_results,
    process_command_spec,
)

from ansible_collections.o0_o.posix.plugins.module_utils.command_spec import (
    COMMAND_SPEC,
    COMPLIANCE_COMMAND_SPEC,
)
from ansible_collections.o0_o.posix.plugins.module_utils.command_utils import (
    process_command_lookups,
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

# Required commands for XCU (Shell & Utilities) compliance
XCU_REQUIRED_COMMANDS = frozenset(
    {
        # Shell
        "sh",
        # Special built-in utilities (XCU 2.14)
        ":",
        ".",
        "break",
        "continue",
        "eval",
        "exec",
        "exit",
        "export",
        "readonly",
        "return",
        "set",
        "shift",
        "times",
        "trap",
        "unset",
        # Regular built-in utilities
        "alias",
        "bg",
        "cd",
        "command",
        "false",
        "fg",
        "getopts",
        "hash",
        "jobs",
        "kill",
        "pwd",
        "read",
        "true",
        "type",
        "ulimit",
        "umask",
        "unalias",
        "wait",
        # Reserved words (XCU 2.4)
        "case",
        "do",
        "done",
        "elif",
        "else",
        "esac",
        "fi",
        "for",
        "if",
        "in",
        "then",
        "until",
        "while",
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
        # Other utilities
        "[",
        "env",
        "expr",
        "id",
        "printf",
        "test",
        "tty",
        "uname",
        "xargs",
        # Archiving
        "tar",
    }
)

# Required commands for XSI (X/Open System Interfaces) compliance
XSI_REQUIRED_COMMANDS = frozenset(
    {
        "getconf",
        "ipcs",
        "ipcrm",
        "pax",
    }
)


@typechecked
def get_compliance_command_requests() -> list[dict[str, Any]]:
    """Build command requests for compliance checks.

    Generates one `command -v` request per required command using list
    kwargs, plus getconf and sh_test commands from COMPLIANCE_COMMAND_SPEC.

    :returns list[dict[str, Any]]: Command requests for run plugin
    """
    requests = []

    # Command lookups - one request per command via list kwarg
    all_cmds = list(XCU_REQUIRED_COMMANDS | XSI_REQUIRED_COMMANDS)
    lookup_requests = process_command_spec(
        COMMAND_SPEC,
        cmd_type="lookup_command",
        cmd=all_cmds,
    )
    requests.extend(lookup_requests)

    # Getconf and sh_test commands
    compliance_requests = process_command_spec(COMPLIANCE_COMMAND_SPEC)
    requests.extend(compliance_requests)

    return requests


@typechecked
def process_all_compliance_command_results(
    cmds_completed: list[dict[str, Any]],
) -> tuple[dict[str, Any], list[Exception]]:
    """Process compliance command results through their parsers.

    Takes command results from run plugin, calls the appropriate
    parser for each command type, and merges the partial results into
    the facts both compliance producers publish: ``o0_os.compliance``,
    ``o0_os.shells``, ``o0_paths``, and ``o0_missing.commands``.

    :param list[dict[str, Any]] cmds_completed: List of command result
        dicts, each containing 'type', 'implementation', 'rc', 'stdout',
        and optionally 'parser' from the command spec
    :returns tuple[dict[str, Any], list[Exception]]: Tuple of
        (facts, errors) where facts holds the o0_os, o0_paths, and
        o0_missing namespaces
    """
    # Initialize compliance dict with standard metadata
    compliance = {
        "xsh": XSH.copy(),
        "xcu": XCU.copy(),
        "xsi": XSI.copy(),
        "posix": POSIX.copy(),
        "sus": SUS.copy(),
    }

    # Standards with required commands
    for standard in ["xcu", "xsi"]:
        compliance[standard]["canaries"] = {"missing": []}

    # Parse all command results through their registered parsers
    processed_results = process_all_command_results(cmds_completed)

    # Process command lookups
    lookup_results = processed_results["lookup_command"]
    result, errors = process_command_lookups(lookup_results)
    missing = result["missing_commands"]

    # Only process getconf results if getconf is available
    if "getconf" in missing:
        compliance["xsi"]["supported"] = False
        compliance["xsi"]["canaries"] = {"missing": ["getconf"]}

    else:
        cmd_type = "xsi_support"
        support_result = processed_results[cmd_type]
        parsed = support_result["parsed"]

        if parsed:
            compliance["xsi"].update(parsed)
            getconf_var = support_result["command"][1]
            getconf_val = support_result["stdout_lines"][0]
            compliance["xsi"]["canaries"] = {
                "getconf": {getconf_var: getconf_val},
            }
            errors.extend(support_result.pop("errors", []))
        else:
            # busybox getconf exits nonzero for variables it does
            # not know, so an unanswerable probe is the platform
            # answering no; the null canary records that it was asked
            getconf_var = support_result["command"][1]
            compliance["xsi"]["supported"] = False
            compliance["xsi"]["canaries"] = {
                "getconf": {getconf_var: None},
            }

        for standard in ["xsh", "xcu", "xsi"]:
            cmd_type = f"{standard}_version"
            version_result = processed_results[cmd_type]
            parsed = version_result["parsed"]

            # Fallback: _POSIX2_VERSION may not exist on some
            # systems (e.g. Debian/glibc) since POSIX.2 was
            # merged into POSIX.1. Use _POSIX_VERSION instead.
            if not parsed and standard == "xcu":
                xsh_result = processed_results["xsh_version"]
                parsed = xsh_result["parsed"]
                if parsed:
                    version_result = xsh_result

            if parsed and compliance[standard].get("supported") is not False:
                compliance[standard].update(parsed)
                getconf_var = version_result["command"][1]
                getconf_val = version_result["stdout_lines"][0]
                compliance[standard]["canaries"] = {
                    "getconf": {getconf_var: getconf_val},
                }
                errors.extend(version_result.pop("errors", []))

    for cmd in sorted(missing):
        if cmd in XCU_REQUIRED_COMMANDS:
            if compliance["xcu"].get("supported") is True:
                compliance["xcu"]["supported"] = "partial"
            canary = {
                "canaries": {
                    "missing": [cmd],
                },
            }
            compliance["xcu"] = merge_hash(
                compliance["xcu"], canary, recursive=True, list_merge="append"
            )
        elif cmd in XSI_REQUIRED_COMMANDS:
            if compliance["xsi"].get("supported") is True:
                compliance["xsi"]["supported"] = "partial"
            canary = {
                "canaries": {
                    "missing": [cmd],
                },
            }
            compliance["xsi"] = merge_hash(
                compliance["xsi"], canary, recursive=True, list_merge="append"
            )

    # POSIX requires both XSH (system interfaces) and XCU (shell/utilities)
    xsh_support = compliance["xsh"].get("supported")
    xcu_support = compliance["xcu"].get("supported")
    if xsh_support is True and xcu_support is True:
        compliance["posix"]["supported"] = True
    elif xsh_support is False and xcu_support is False:
        compliance["posix"]["supported"] = False
    elif xsh_support is not None and xcu_support is not None:
        compliance["posix"]["supported"] = "partial"

    # SUS requires full POSIX plus XSI extensions
    posix_support = compliance["posix"].get("supported")
    xsi_support = compliance["xsi"].get("supported")
    if posix_support is True and xsi_support is True:
        compliance["sus"]["supported"] = True
        # SUS version = XSI Issue - 3 (e.g., Issue 7 = SUSv4)
        xsi_issue = compliance["xsi"].get("version", {}).get("issue")
        if xsi_issue:
            xsi_issue = int(xsi_issue)
            sus_version = xsi_issue - 3
            compliance["sus"]["version"] = {
                "issue": xsi_issue,
                "id": sus_version,
                "pretty": f"v{sus_version}",
            }
    elif xsi_support in [True, "partial"]:
        compliance["sus"]["supported"] = "partial"
    else:
        compliance["sus"]["supported"] = False

    result["paths"]["/bin/sh"] = {}

    # The processor names its own facts, so the two producers that
    # share it cannot disagree about where they land.
    facts = {
        "o0_os": {
            "compliance": compliance,
            "shells": result["shells"],
        },
        "o0_paths": result["paths"],
        "o0_missing": {"commands": result["missing_commands"]},
    }

    return facts, errors
