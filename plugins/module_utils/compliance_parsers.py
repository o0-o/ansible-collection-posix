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

from ansible_collections.o0_o.utils.plugins.module_utils.typeguard_compat import (  # noqa: E501
    typechecked,
)


# X/Open Issue -> POSIX version (YYYYMM format)
# Issue 6 = SUSv3/POSIX.1-2001, Issue 7 = SUSv4/POSIX.1-2008, etc.
XOPEN_POSIX_VERSION_MAP = {
    "600": 200112,  # POSIX.1-2001
    "700": 200809,  # POSIX.1-2008
    "800": 202406,  # POSIX.1-2024
}


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
def _parse_posix_standard(
    output: str,
    e_prefix: str,
    getconf_var: Optional[str],
) -> tuple[Optional[dict[str, Any]], Optional[list[Exception]]]:
    """Parse POSIX version string into compliance dict fragment.

    Validates and parses a POSIX version string (YYYYMM format) into a
    partial compliance dict. Used by XSH, XCU, and XOPEN version parsers.

    :param str output: Raw getconf output (POSIX version string)
    :param str e_prefix: Error prefix for error messages
    :param Optional[str] getconf_var: Name of the getconf variable to
        record in canaries, or None to skip canary recording
    :returns tuple: (partial_compliance_dict, errors_or_none) where the
        dict contains 'supported', 'version', and optionally 'canaries'
    """
    result = {}
    errors = []

    # Record raw getconf output for debugging/verification
    if getconf_var:
        result["canaries"] = {
            "getconf": {
                getconf_var: output,
            },
        }

    getconf_version = _normalize_output(output)

    if getconf_version == -1:
        return {"supported": False}, None

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
def _parse_xsh_version(
    rc: int,
    output: str,
    e_prefix: str,
) -> tuple[Optional[dict[str, Any]], Optional[list[Exception]]]:
    """Parse _POSIX_VERSION getconf output.

    Returns partial compliance dict with POSIX.1 (XSH) information.

    :param int rc: Command return code
    :param str output: Raw command output
    :param str e_prefix: Error prefix for error messages
    :returns tuple: (partial_compliance_dict, errors_or_none)
    """
    del rc

    result = {}
    xsh, errors = _parse_posix_standard(output, e_prefix, "_POSIX_VERSION")

    if xsh:
        result["xsh"] = xsh
        return result, errors
    else:
        return None, errors


@typechecked
def _parse_xcu_version(
    rc: int,
    output: str,
    e_prefix: str,
) -> tuple[Optional[dict[str, Any]], Optional[list[Exception]]]:
    """Parse _POSIX2_VERSION getconf output.

    Returns partial compliance dict with POSIX.1 (XCU) information.

    :param int rc: Command return code
    :param str output: Raw command output
    :param str e_prefix: Error prefix for error messages
    :returns tuple: (partial_compliance_dict, errors_or_none)
    """
    del rc
    result = {}
    xcu, errors = _parse_posix_standard(output, e_prefix, "_POSIX2_VERSION")

    if xcu:
        result["xcu"] = xcu
        return result, errors
    else:
        return None, errors


@typechecked
def _parse_xopen_support(
    rc: int,
    output: str,
    e_prefix: str,
) -> tuple[Optional[dict[str, Any]], Optional[list[Exception]]]:
    """Parse _XOPEN_UNIX getconf output.

    Returns partial compliance dict with XSI support flag.
    """
    del rc

    result = {
        "xsi": {
            "canaries": {
                "getconf": {
                    "_XOPEN_UNIX": output,
                }
            }
        }
    }
    errors = []

    if _normalize_output(output) == -1:
        result["xsi"]["supported"] = False
        return result, None

    if output == "1":
        result["xsi"]["supported"] = True
        return result, None

    errors.append(
        ValueError(
            f"{e_prefix}Malformed X/Open support value, should be 1 if "
            f"supported: f{repr(output)}"
        )
    )
    return None, errors


@typechecked
def _parse_xopen_versions(
    rc: int,
    output: str,
    e_prefix: str,
) -> tuple[Optional[dict[str, Any]], Optional[list[Exception]]]:
    """Parse _XOPEN_VERSION getconf output.

    Returns partial compliance dict with SUS information.

    :param int rc: Command return code
    :param str output: Raw command output
    :param str e_prefix: Error prefix for error messages
    :returns tuple: (partial_compliance_dict, errors_or_none)
    """
    del rc

    # _XOPEN_VERSION provides info for all three standards at once
    result = {
        "xsi": {},
        "xsh": {},
        "xcu": {},
    }
    errors = []

    getconf_version = _normalize_output(output)

    if getconf_version == -1:
        return {"supported": False}, None

    # Validate against known X/Open versions (600, 700, 800)
    valid_xopen_versions = XOPEN_POSIX_VERSION_MAP
    if getconf_version not in valid_xopen_versions:
        errors.append(
            ValueError(
                f"{e_prefix}Unrecognized XOPEN version from getconf "
                f"(known versions are {valid_xopen_versions}): "
                f"{repr(getconf_version)}"
            )
        )

    if errors:
        return None, errors

    # Populate each standard's compliance info from the X/Open version
    for standard in result:
        if standard == "xsi":
            # XSI issue number is version/100 (e.g., 700 -> Issue 7)
            xsi_issue = int(getconf_version) / 100
            result["xsi"]["supported"] = True
            result["xsi"]["version"] = {
                "issue": xsi_issue,
                "pretty": f"Issue {xsi_issue}",
            }
        else:
            posix_version = XOPEN_POSIX_VERSION_MAP[getconf_version]
            result[standard], std_errors = _parse_posix_standard(
                str(posix_version),
                e_prefix,
                None,
            )
            if std_errors:
                errors.extend(std_errors)

        result[standard]["canaries"] = {
            "getconf": {
                "_XOPEN_VERSION": output,
            },
        }

    return result, errors
