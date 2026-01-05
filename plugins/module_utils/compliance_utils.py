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

"""POSIX/SUS compliance detection utilities.

Standalone functions for gathering and processing POSIX, X/Open, and SUS
compliance information using getconf commands. These functions are designed
to be used independently of ActionBase classes.

Each getconf variable has its own parser (defined in parsers.py) that returns
a partial compliance dict. The partial dicts are merged here to build the
complete compliance picture.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Optional

from ansible_collections.o0_o.core.plugins.module_utils.command_utils import (
    process_command_spec,
)
from ansible_collections.o0_o.posix.plugins.module_utils.command_spec import (
    COMMAND_SPEC,
)
from ansible_collections.o0_o.posix.plugins.module_utils.parsers import (
    POSIX,
    POSIX_UTILITIES,
    POSIX_VERSIONS,
    XOPEN_VERSIONS,
    _is_undefined,
)

# Command types for compliance checks
COMPLIANCE_COMMANDS = (
    "getconf_posix_version",
    "getconf_posix2_version",
    "getconf_xopen_unix",
    "getconf_xopen_version",
    "getconf_xopen_xcu_version",
)


def get_compliance_commands() -> dict[str, list[str]]:
    """Return tagged commands needed for compliance facts.

    Uses COMMAND_SPEC to build getconf commands for each compliance
    variable. Returns dict mapping tags to commands for batching.

    :returns dict[str, list[str]]: Dict mapping tags to commands
    """
    commands = {}
    for cmd_type in COMPLIANCE_COMMANDS:
        cmd_requests = process_command_spec(COMMAND_SPEC, cmd_type)
        if cmd_requests:
            commands[cmd_type] = cmd_requests[0]["command"]
    return commands


def merge_compliance_results(
    partial_results: list[tuple[dict[str, Any], Optional[list[Exception]]]],
) -> tuple[dict[str, Any], list[Exception], list[str]]:
    """Merge partial compliance dicts into complete compliance structure.

    Handles interdependencies between getconf values, such as inferring
    POSIX2 compliance from POSIX1 when XCU_VERSION is defined but invalid.

    :param list[tuple[dict[str, Any], Optional[list[Exception]]]]
        partial_results: List of (partial_dict, errors) tuples from parsers
    :returns tuple[dict[str, Any], list[Exception], list[str]]: Tuple of
        (compliance_dict, errors_list, debug_messages_list)
    """
    compliance: dict[str, Any] = {}
    errors: list[Exception] = []
    debug_msgs: list[str] = []
    raw_values: dict[str, Optional[str]] = {}

    # Collect raw values and errors from all partial results
    for partial, partial_errors in partial_results:
        if "_raw" in partial:
            raw_values.update(partial["_raw"])
        if partial_errors:
            errors.extend(partial_errors)

    # Merge POSIX.1 (XSH) from posix_version
    for partial, _errors in partial_results:
        if "posix" in partial:
            compliance["posix"] = partial["posix"]
            break

    # Merge POSIX.2 (XCU) - check for direct or inferred
    posix2_partial = None
    for partial, _errors in partial_results:
        if "posix2" in partial:
            posix2_partial = partial["posix2"]
            break

    # Get raw values for inference logic
    posix_version = raw_values.get("posix_version")
    posix2_version = raw_values.get("posix2_version")
    xopen_xcu_version = raw_values.get("xopen_xcu_version")

    # If POSIX2 is undefined but XCU_VERSION exists and is invalid,
    # infer POSIX2 from POSIX1
    if posix2_partial is None and _is_undefined(posix2_version):
        if (
            not _is_undefined(xopen_xcu_version)
            and xopen_xcu_version not in POSIX_VERSIONS
            and xopen_xcu_version not in XOPEN_VERSIONS
        ):
            if posix_version is not None and posix_version in POSIX_VERSIONS:
                debug_msgs.append(
                    f"POSIX2 undefined but "
                    f"_XOPEN_XCU_VERSION={xopen_xcu_version} "
                    f"(not a valid POSIX/XOPEN version), "
                    f"assuming POSIX2={posix_version}"
                )
                # Create inferred POSIX2 entry
                posix2_partial = {
                    "version": posix_version,
                    "xcu": POSIX_UTILITIES.copy(),
                    "inferred": True,
                }
                posix2_partial["xcu"].update(
                    deepcopy(POSIX_VERSIONS[posix_version])
                )
                posix2_partial["xcu"]["version"]["getconf"] = {
                    "_POSIX2_VERSION": None,
                    "_XOPEN_XCU_VERSION": xopen_xcu_version,
                }
                posix2_partial["xcu"]["note"] = (
                    f"Assuming _POSIX_VERSION ({posix_version}) applies "
                    f"because _XOPEN_XCU_VERSION is defined "
                    f"({xopen_xcu_version}) but appears to be invalid"
                )

    # Add POSIX2 to compliance if we have it
    if posix2_partial is not None:
        if "posix" not in compliance:
            compliance["posix"] = POSIX.copy()
            compliance["posix"]["components"] = {}
        elif "components" not in compliance["posix"]:
            compliance["posix"]["components"] = {}

        compliance["posix"]["components"]["xcu"] = posix2_partial["xcu"]

        # Update getconf if not inferred
        if not posix2_partial.get("inferred"):
            # Include XCU_VERSION in getconf if it exists
            compliance["posix"]["components"]["xcu"]["version"]["getconf"][
                "_XOPEN_XCU_VERSION"
            ] = xopen_xcu_version

    # Merge XSI indicator if POSIX compliance exists
    for partial, _errors in partial_results:
        if "xsi" in partial and "posix" in compliance:
            if "components" not in compliance["posix"]:
                compliance["posix"]["components"] = {}
            compliance["posix"]["components"]["xsi"] = partial["xsi"]
            break

    # Merge SUS compliance
    for partial, _errors in partial_results:
        if "sus" in partial:
            compliance["sus"] = partial["sus"]
            # Add _XOPEN_UNIX to sus level
            xopen_unix = raw_values.get("xopen_unix")
            compliance["sus"]["getconf"] = {"_XOPEN_UNIX": xopen_unix}
            break

    return compliance, errors, debug_msgs


def process_compliance_results(
    commands_results: dict[str, dict[str, Any]],
) -> tuple[dict[str, Any], list[Exception], list[str]]:
    """Process compliance command results through their parsers.

    Takes tagged command results from run plugin, calls the appropriate
    parser for each command type, and merges the partial results.

    :param dict[str, dict[str, Any]] commands_results: Dict mapping
        command tags (e.g., "getconf_posix_version") to their results
        containing 'rc' and 'stdout' keys
    :returns tuple[dict[str, Any], list[Exception], list[str]]: Tuple of
        (compliance_dict, errors_list, debug_messages_list)
    """
    partial_results: list[tuple[dict[str, Any], Optional[list[Exception]]]] = (
        []
    )

    for cmd_type in COMPLIANCE_COMMANDS:
        if cmd_type not in commands_results:
            continue

        cmd_result = commands_results[cmd_type]
        rc = cmd_result.get("rc", 1)
        stdout = cmd_result.get("stdout", "")

        # Get parser from COMMAND_SPEC
        spec = COMMAND_SPEC.get("posix", {}).get(cmd_type, {})
        parser = spec.get("parser")

        if parser:
            parsed, errors = parser(rc, stdout, cmd_type)
            partial_results.append((parsed, errors))

    return merge_compliance_results(partial_results)


def format_compliance_message(compliance: dict[str, Any]) -> str:
    """Format a human-readable compliance status message.

    :param dict[str, Any] compliance: Compliance facts dictionary
    :returns str: Human-readable status message
    """
    if "sus" in compliance:
        # If SUS compliant, just mention SUS (it includes POSIX)
        return (
            f"System is compliant with "
            f"{compliance['sus']['version']['name']}"
        )
    elif "posix" in compliance:
        # Otherwise mention POSIX with components
        components = []
        if "components" in compliance["posix"]:
            for comp_key in ["xsh", "xcu", "xsi"]:
                if comp_key in compliance["posix"]["components"]:
                    components.append(comp_key.upper())
        if components:
            return f"System is POSIX-compliant ({', '.join(components)})"
        else:
            return "System is POSIX-compliant"
    else:
        return "System is not POSIX-compliant"
