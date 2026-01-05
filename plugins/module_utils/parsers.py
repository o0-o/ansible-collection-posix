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
    (parsed_output, error_list_or_none)

These parsers are used in COMMAND_SPEC entries for compliance detection.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Optional


# Standards metadata (duplicated here to avoid circular import)
SUS = {
    "name": "Single UNIX Specification",
    "abbreviation": "SUS",
    "description": (
        "Unified UNIX standard combining POSIX with XSI extensions"
    ),
}

POSIX = {
    "name": "Portable Operating System Interface",
    "abbreviation": "POSIX",
    "description": (
        "IEEE standard for compatibility between operating systems"
    ),
}

XSH = {
    "name": "System Interfaces",
    "abbreviation": "XSH",
    "description": "POSIX System Interfaces and Headers",
}

POSIX_UTILITIES = {
    "name": "Shell & Utilities",
    "abbreviation": "XCU",
    "description": "POSIX Shell and Utilities",
}

# Version mappings
XOPEN_VERSIONS = {
    "600": {"version": {"id": 3, "name": "SUSv3"}},
    "700": {"version": {"id": 4, "name": "SUSv4"}},
    "800": {"version": {"id": 5, "name": "SUSv5"}},
}

POSIX_VERSIONS = {
    "200112": {"version": {"id": "2001", "name": "POSIX.1-2001"}},
    "200809": {"version": {"id": "2008", "name": "POSIX.1-2008"}},
    "202405": {"version": {"id": "2024", "name": "POSIX.1-2024"}},
}


def _is_undefined(value: Optional[str]) -> bool:
    """Check if a getconf value is undefined or invalid."""
    return value is None or value == "" or value == "-1"


def parse_posix_version(
    rc: int,
    output: str,
    e_prefix: str,
) -> tuple[dict[str, Any], Optional[list[Exception]]]:
    """Parse _POSIX_VERSION getconf output.

    Returns partial compliance dict with POSIX.1 (XSH) information.

    :param int rc: Command return code
    :param str output: Raw command output
    :param str e_prefix: Error prefix for error messages
    :returns tuple: (partial_compliance_dict, errors_or_none)
    """
    value: Optional[str] = output.strip() if rc == 0 else None
    errors: Optional[list[Exception]] = None

    result: dict[str, Any] = {"_raw": {"posix_version": value}}

    if value is not None and value in POSIX_VERSIONS:
        result["posix"] = POSIX.copy()
        result["posix"]["components"] = {}
        result["posix"]["components"]["xsh"] = XSH.copy()
        result["posix"]["components"]["xsh"].update(
            deepcopy(POSIX_VERSIONS[value])
        )
        result["posix"]["components"]["xsh"]["version"]["getconf"] = {
            "_POSIX_VERSION": value
        }
    elif not _is_undefined(value):
        errors = [
            ValueError(
                f"{e_prefix}Unrecognized POSIX.1 version: {value}. "
                f"Known versions: {', '.join(POSIX_VERSIONS.keys())}"
            )
        ]

    return result, errors


def parse_posix2_version(
    rc: int,
    output: str,
    e_prefix: str,
) -> tuple[dict[str, Any], Optional[list[Exception]]]:
    """Parse _POSIX2_VERSION getconf output.

    Returns partial compliance dict with POSIX.2 (XCU) information.

    :param int rc: Command return code
    :param str output: Raw command output
    :param str e_prefix: Error prefix for error messages
    :returns tuple: (partial_compliance_dict, errors_or_none)
    """
    value: Optional[str] = output.strip() if rc == 0 else None
    errors: Optional[list[Exception]] = None

    result: dict[str, Any] = {"_raw": {"posix2_version": value}}

    if value is not None and value in POSIX_VERSIONS:
        result["posix2"] = {
            "version": value,
            "xcu": POSIX_UTILITIES.copy(),
        }
        result["posix2"]["xcu"].update(deepcopy(POSIX_VERSIONS[value]))
        result["posix2"]["xcu"]["version"]["getconf"] = {
            "_POSIX2_VERSION": value
        }
    elif not _is_undefined(value):
        errors = [
            ValueError(
                f"{e_prefix}Unrecognized POSIX.2 version: {value}. "
                f"Known versions: {', '.join(POSIX_VERSIONS.keys())}"
            )
        ]

    return result, errors


def parse_xopen_unix(
    rc: int,
    output: str,
    e_prefix: str,
) -> tuple[dict[str, Any], Optional[list[Exception]]]:
    """Parse _XOPEN_UNIX getconf output.

    Returns partial compliance dict with XSI support flag.

    :param int rc: Command return code
    :param str output: Raw command output
    :param str e_prefix: Error prefix for error messages
    :returns tuple: (partial_compliance_dict, errors_or_none)
    """
    del e_prefix  # unused - no error conditions for this parser
    value: Optional[str] = output.strip() if rc == 0 else None

    result: dict[str, Any] = {"_raw": {"xopen_unix": value}}

    if not _is_undefined(value) and value != "0":
        try:
            if int(value) > 0:  # type: ignore[arg-type]
                result["xsi"] = {
                    "name": "X/Open System Interface",
                    "abbreviation": "XSI",
                    "description": "Extensions to POSIX for UNIX systems",
                    "enabled": True,
                    "getconf": {"_XOPEN_UNIX": value},
                }
        except (ValueError, TypeError):
            pass

    return result, None


def parse_xopen_version(
    rc: int,
    output: str,
    e_prefix: str,
) -> tuple[dict[str, Any], Optional[list[Exception]]]:
    """Parse _XOPEN_VERSION getconf output.

    Returns partial compliance dict with SUS information.

    :param int rc: Command return code
    :param str output: Raw command output
    :param str e_prefix: Error prefix for error messages
    :returns tuple: (partial_compliance_dict, errors_or_none)
    """
    value: Optional[str] = output.strip() if rc == 0 else None
    errors: Optional[list[Exception]] = None

    result: dict[str, Any] = {"_raw": {"xopen_version": value}}

    if value is not None and value in XOPEN_VERSIONS:
        result["sus"] = SUS.copy()
        result["sus"].update(deepcopy(XOPEN_VERSIONS[value]))
        result["sus"]["version"]["getconf"] = {"_XOPEN_VERSION": value}
    elif not _is_undefined(value):
        errors = [
            ValueError(
                f"{e_prefix}Unrecognized X/Open version: {value}. "
                f"Known versions: {', '.join(XOPEN_VERSIONS.keys())}"
            )
        ]

    return result, errors


def parse_xopen_xcu_version(
    rc: int,
    output: str,
    e_prefix: str,
) -> tuple[dict[str, Any], Optional[list[Exception]]]:
    """Parse _XOPEN_XCU_VERSION getconf output.

    Returns raw value for use in inferring POSIX2 compliance.

    :param int rc: Command return code
    :param str output: Raw command output
    :param str e_prefix: Error prefix for error messages
    :returns tuple: (partial_compliance_dict, errors_or_none)
    """
    del e_prefix  # unused - no error conditions for this parser
    value: Optional[str] = output.strip() if rc == 0 else None

    return {"_raw": {"xopen_xcu_version": value}}, None
