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

"""Parser functions for POSIX/SUS compliance detection.

Parser functions for getconf commands that return partial compliance dicts.
Each parser receives (rc, output, e_prefix) and returns:
    (parsed_output, errors_or_none)
"""

from __future__ import annotations

from typing import Any, Optional, Union

from ansible_collections.o0_o.utils.plugins.module_utils import typechecked


@typechecked
def _normalize_output(value: Union[str, int]) -> Union[str, int]:
    """Normalize getconf output to detect unsupported features.

    getconf returns -1, empty string, or "undefined" when a feature is
    not supported. This function normalizes all these to -1 for
    consistent checking.

    :param Union[str, int] value: Raw getconf output value
    :returns Union[str, int]: -1 if unsupported, otherwise the
        original value unchanged
    """
    if value in (-1, "-1", "", "undefined"):
        return -1
    return value


@typechecked
def _parse_posix_version(
    output: str,
    e_prefix: str,
) -> tuple[Optional[dict[str, Any]], Optional[list[Exception]]]:
    """Parse POSIX version string into compliance dict fragment.

    Validates and parses a POSIX version string (YYYYMM format) into a
    partial compliance dict. Used by XSH, XCU, and XOPEN version parsers.

    :param str output: Raw getconf output (POSIX version string)
    :param str e_prefix: Error prefix for error messages
    :returns tuple: (partial_compliance_dict, errors_or_none) where the
        dict contains 'supported' and, where the host named one,
        'version'
    """
    result = {}
    errors = []

    getconf_version = _normalize_output(output)

    if getconf_version == -1:
        result["supported"] = False
        return result, None

    # POSIX versions are YYYYMM format, first standard was 199009
    try:
        if int(getconf_version, 10) < 199009:
            errors.append(
                ValueError(
                    f"{e_prefix}Malformed POSIX version from getconf "
                    f"(should be >= 199009): {repr(getconf_version)}"
                )
            )
    except ValueError:
        errors.append(
            ValueError(
                f"{e_prefix}Malformed POSIX version from getconf "
                f"(should be an integer): {repr(getconf_version)}"
            )
        )

    if len(getconf_version) != 6:
        errors.append(
            ValueError(
                f"{e_prefix}Malformed POSIX version from getconf "
                f"(should have a length of 6): {repr(getconf_version)}"
            )
        )

    if errors:
        return None, errors

    year = getconf_version[:4]

    result["supported"] = True
    result["version"] = {
        "id": year,
        "name": f"POSIX.1-{year}",
    }

    return result, None


@typechecked
def _parse_xopen_support(
    output: str,
    e_prefix: str,
) -> tuple[Optional[dict[str, Any]], Optional[list[Exception]]]:
    """Parse _XOPEN_UNIX getconf output.

    Returns partial compliance dict with XSI support flag.

    :param str output: Raw command output
    :param str e_prefix: Error prefix for error messages
    :returns tuple: (partial_compliance_dict, errors_or_none)
    """
    result = {}
    errors = []

    if _normalize_output(output) == -1:
        result["supported"] = False
        return result, None

    if output == "1":
        result["supported"] = True
        return result, None

    errors.append(
        ValueError(
            f"{e_prefix}Malformed X/Open support value, should be 1 if "
            f"supported: f{repr(output)}"
        )
    )
    return None, errors


@typechecked
def _parse_xopen_version(
    output: str,
    e_prefix: str,
) -> tuple[Optional[dict[str, Any]], Optional[list[Exception]]]:
    """Parse _XOPEN_VERSION getconf output.

    Returns partial compliance dict with XSI and XSH information.
    Note: XCU is NOT populated here - XCU conformance is exclusively
    determined by _POSIX2_VERSION.

    :param str output: Raw command output
    :param str e_prefix: Error prefix for error messages
    :returns tuple: (partial_compliance_dict, errors_or_none)
    """
    result = {}
    errors = []

    getconf_version = _normalize_output(output)

    if getconf_version == -1:
        return {"supported": False}, None

    try:
        if int(getconf_version) < 500 or int(getconf_version) % 100 != 0:
            errors.append(
                ValueError(
                    f"{e_prefix}Malformed XOPEN version from getconf "
                    "(known versions are >= 500 and divisible by 100: "
                    f"{repr(getconf_version)}"
                )
            )
    except TypeError:
        raise TypeError(
            f"{e_prefix}Malformed XOPEN version from getconf "
            "(known versions are >= 500 and divisible by 100: "
            f"{repr(getconf_version)}"
        )

    if errors:
        return None, errors

    # Populate XSI info
    xsi_issue = int(getconf_version) // 100
    result["supported"] = True
    result["version"] = {
        "issue": xsi_issue,
        "pretty": f"Issue {xsi_issue}",
    }

    return result, errors


@typechecked
def _parse_sh_test(
    output: str,
    e_prefix: str,
) -> tuple[Optional[dict[str, Any]], Optional[list[Exception]]]:
    """Validate POSIX sh test output.

    The sh_test command runs a basic POSIX shell compatibility test:
    `x=1; [ "$x" = 1 ] && printf "posix sh"`

    If the shell is POSIX-compliant, the output should be exactly
    "posix sh".

    :param str output: Raw command output
    :param str e_prefix: Error prefix for error messages
    :returns tuple: (partial_compliance_dict, errors_or_none)
    """
    result = {}

    if output == "posix sh":
        result["sh_posix_compliant"] = True
        return result, None

    # Shell test failed or produced unexpected output
    errors = []
    if output == "":
        result["sh_posix_compliant"] = False
    else:
        errors.append(
            ValueError(
                f"{e_prefix}Unexpected sh test output, expected 'posix sh': "
                f"{repr(output)}"
            )
        )
        result["sh_posix_compliant"] = False

    return result, errors if errors else None
