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

"""Mixin for gathering POSIX/SUS compliance facts."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict

from ansible_collections.o0_o.posix.plugins.module_utils.command_spec import (
    COMMAND_SPEC,
)
from ansible_collections.o0_o.posix.plugins.module_utils.posix_action_base import (  # noqa: E501
    PosixActionBase,
)


class CompliancePosixActionBase(PosixActionBase):
    """Mixin for gathering POSIX/SUS compliance information.

    Provides methods to gather and process POSIX, X/Open, and SUS
    compliance information using getconf commands. Can be used
    standalone or as part of a coordinated facts gathering operation.
    """

    # Override CoreActionBase.COMMAND_SPEC with POSIX-extended specs
    COMMAND_SPEC = COMMAND_SPEC

    # Standards metadata
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

    XSI = {
        "name": "X/Open System Interface",
        "abbreviation": "XSI",
        "description": "Extensions to POSIX for UNIX systems",
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
        # Don't include legacy versions (XPG3, XPG4, SUSv2)
        "600": {"version": {"id": 3, "name": "SUSv3"}},  # SUSv3 (2001)
        "700": {  # SUSv4 (2008, includes 2017 revision)
            "version": {"id": 4, "name": "SUSv4"}
        },
        # POSIX.1-2024 (Issue 8) - anticipated value
        "800": {"version": {"id": 5, "name": "SUSv5"}},
    }

    POSIX_VERSIONS = {
        # Don't include legacy POSIX versions before 2001
        # (POSIX.1-1988, POSIX.1-1990, POSIX.1-1996)
        "200112": {"version": {"id": "2001", "name": "POSIX.1-2001"}},
        "200809": {"version": {"id": "2008", "name": "POSIX.1-2008"}},
        # POSIX.1-2017 is a revision of 2008, likely keeps same
        # getconf value
        # POSIX.1-2024 (Issue 8) - anticipated value
        "202405": {"version": {"id": "2024", "name": "POSIX.1-2024"}},
    }

    # Getconf variables to query for compliance detection
    COMPLIANCE_VARIABLES = (
        "_POSIX_VERSION",
        "_POSIX2_VERSION",
        "_XOPEN_UNIX",
        "_XOPEN_VERSION",
        "_XOPEN_XCU_VERSION",
    )

    def _get_compliance_commands(self) -> dict[str, list[str]]:
        """Return tagged commands needed for compliance facts.

        Uses COMMAND_SPEC to build getconf commands for each compliance
        variable. Returns dict mapping tags to commands for batching.

        :returns dict[str, list[str]]: Dict mapping tags to commands
        """
        commands = {}
        for variable in self.COMPLIANCE_VARIABLES:
            cmd_requests = self._process_command_spec(
                "getconf", variable=variable
            )
            if cmd_requests:
                # Tag is variable name without leading underscore, lowercase
                tag = variable.lstrip("_").lower()
                commands[tag] = cmd_requests[0]["command"]
        return commands

    def _process_compliance_results(
        self, commands_results: Dict[str, Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Process command results into compliance facts.

        Takes the results from executing compliance commands and
        processes them into a structured compliance dictionary with
        POSIX, SUS, and XSI information.

        :param Dict[str, Dict[str, Any]] commands_results: Dictionary
            mapping tag -> command result (each result has rc, stdout,
            stderr, cmd keys)
        :returns Dict[str, Any]: Compliance facts dictionary
        """
        compliance = {}

        # Extract values from results (treat errors as "undefined")
        values = {}
        for tag, result in commands_results.items():
            if result["rc"] == 0:
                values[tag] = result["stdout"].strip()
            else:
                values[tag] = "undefined"

        # Process POSIX.1 (XSH - System Interfaces and Headers)
        posix1_version = values.get("posix_version", "undefined")
        if posix1_version in self.POSIX_VERSIONS:
            if "posix" not in compliance:
                compliance["posix"] = self.POSIX.copy()
                compliance["posix"]["components"] = {}
            compliance["posix"]["components"]["xsh"] = self.XSH.copy()
            compliance["posix"]["components"]["xsh"].update(
                deepcopy(self.POSIX_VERSIONS[posix1_version])
            )
            compliance["posix"]["components"]["xsh"]["version"]["getconf"] = {
                "_POSIX_VERSION": posix1_version
            }
        elif posix1_version not in ["undefined", "", "-1"]:
            self._display.warning(
                f"[{self.inventory_hostname}] Unrecognized POSIX.1 version: "
                f"{posix1_version}. Known versions: "
                f"{', '.join(self.POSIX_VERSIONS.keys())}"
            )

        # Process POSIX.2 (XCU - Shell and Utilities)
        posix2_version = values.get("posix2_version", "undefined")
        xopen_xcu_version = values.get("xopen_xcu_version", "undefined")
        posix2_assumed = False

        # If POSIX2 is undefined but _XOPEN_XCU_VERSION exists and is
        # not a valid POSIX or XOPEN version, then we can assume
        # POSIX2 = POSIX1
        if posix2_version in ["undefined", "", "-1"]:
            if (
                xopen_xcu_version not in ["undefined", "", "-1"]
                and xopen_xcu_version not in self.POSIX_VERSIONS
                and xopen_xcu_version not in self.XOPEN_VERSIONS
            ):
                if posix1_version in self.POSIX_VERSIONS:
                    posix2_version = posix1_version
                    posix2_assumed = True
                    self._display.vvv(
                        f"POSIX2 undefined but "
                        f"_XOPEN_XCU_VERSION={xopen_xcu_version} "
                        f"(not a valid POSIX/XOPEN version), "
                        f"assuming POSIX2={posix1_version}"
                    )

        if posix2_version in self.POSIX_VERSIONS:
            if "posix" not in compliance:
                compliance["posix"] = self.POSIX.copy()
                compliance["posix"]["components"] = {}
            elif "components" not in compliance["posix"]:
                compliance["posix"]["components"] = {}
            compliance["posix"]["components"][
                "xcu"
            ] = self.POSIX_UTILITIES.copy()
            compliance["posix"]["components"]["xcu"].update(
                deepcopy(self.POSIX_VERSIONS[posix2_version])
            )

            # Always include both _POSIX2_VERSION and
            # _XOPEN_XCU_VERSION in getconf. Use None for undefined
            # values to show what was actually found
            getconf_xcu = {}
            if posix2_assumed:
                # POSIX2 was undefined
                getconf_xcu["_POSIX2_VERSION"] = None
                getconf_xcu["_XOPEN_XCU_VERSION"] = xopen_xcu_version
                compliance["posix"]["components"]["xcu"]["note"] = (
                    f"Assuming _POSIX_VERSION ({posix1_version}) applies "
                    f"because _XOPEN_XCU_VERSION is defined "
                    f"({xopen_xcu_version}) but appears to be invalid"
                )
            else:
                # POSIX2 was defined
                getconf_xcu["_POSIX2_VERSION"] = posix2_version
                # Include XCU_VERSION if it exists (even if undefined)
                if xopen_xcu_version not in ["undefined", "", "-1"]:
                    getconf_xcu["_XOPEN_XCU_VERSION"] = xopen_xcu_version
                else:
                    getconf_xcu["_XOPEN_XCU_VERSION"] = None

            compliance["posix"]["components"]["xcu"]["version"][
                "getconf"
            ] = getconf_xcu
        elif posix2_version not in ["undefined", "", "-1"]:
            self._display.warning(
                f"[{self.inventory_hostname}] Unrecognized POSIX.2 version: "
                f"{posix2_version}. Known versions: "
                f"{', '.join(self.POSIX_VERSIONS.keys())}"
            )

        # Process X/Open compliance
        xopen_support = values.get("xopen_unix", "undefined")
        xopen_version = values.get("xopen_version", "undefined")

        # Add XSI indicator to POSIX components if _XOPEN_UNIX > 0
        if (
            xopen_support not in ["undefined", "", "-1", "0"]
            and "posix" in compliance
        ):
            try:
                if int(xopen_support) > 0:
                    if "components" not in compliance["posix"]:
                        compliance["posix"]["components"] = {}
                    compliance["posix"]["components"]["xsi"] = {
                        "name": "X/Open System Interface",
                        "abbreviation": "XSI",
                        "description": (
                            "Extensions to POSIX for UNIX systems"
                        ),
                        "enabled": True,
                        "getconf": {"_XOPEN_UNIX": xopen_support},
                    }
            except (ValueError, TypeError):
                pass

        # Define SUS only when _XOPEN_VERSION is defined
        if xopen_version in self.XOPEN_VERSIONS:
            compliance["sus"] = self.SUS.copy()
            compliance["sus"].update(
                deepcopy(self.XOPEN_VERSIONS[xopen_version])
            )
            # Add getconf values - _XOPEN_VERSION under version,
            # _XOPEN_UNIX at sus level
            compliance["sus"]["version"]["getconf"] = {
                "_XOPEN_VERSION": xopen_version
            }
            compliance["sus"]["getconf"] = {"_XOPEN_UNIX": xopen_support}
        elif xopen_version not in ["undefined", "", "-1"]:
            self._display.warning(
                f"[{self.inventory_hostname}] Unrecognized X/Open version: "
                f"{xopen_version}. Known versions: "
                f"{', '.join(self.XOPEN_VERSIONS.keys())}"
            )

        return compliance

    def _format_compliance_message(self, compliance: Dict[str, Any]) -> str:
        """Format a human-readable compliance status message.

        :param Dict[str, Any] compliance: Compliance facts dictionary
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
                return (
                    f"System is POSIX-compliant " f"({', '.join(components)})"
                )
            else:
                return "System is POSIX-compliant"
        else:
            return "System is not POSIX-compliant"
