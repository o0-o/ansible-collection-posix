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

from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, Optional

from ansible.errors import AnsibleActionFail, AnsibleConnectionFailure
from ansible.module_utils.common.text.converters import to_text
import yaml
from ansible_collections.o0_o.posix.plugins.action_utils.posix_base import (
    PosixBase,
)


class ActionModule(PosixBase):
    """
    Check POSIX and UNIX standards compliance of the target host.

    This action plugin checks the standards compliance of the target
    system by querying POSIX, X/Open, and SUS compliance information
    using getconf commands. It gracefully handles systems that may not
    have getconf or may not be standards-compliant.

    The module returns success with is_posix=true if the system
    appears to be POSIX-compliant, along with detailed compliance
    information for POSIX (XSH/XCU), SUS, and XSI when available.
    Returns is_posix=false if the system is not POSIX-compliant.
    """

    TRANSFERS_FILES = False
    _requires_connection = True
    _supports_check_mode = True
    _supports_async = False
    _supports_diff = False

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

    def run(
        self,
        tmp: Optional[str] = None,
        task_vars: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Main entry point for the action plugin.

        Tests if the target system is POSIX-compliant by checking for
        POSIX version information using getconf commands.

        :param Optional[str] tmp: Temporary directory path (unused
            in modern Ansible)
        :param Optional[Dict[str, Any]] task_vars: Task variables
            dictionary
        :returns Dict[str, Any]: Standard Ansible result dictionary
            with is_posix boolean and compliance information

        .. note::
           The module tries multiple getconf commands to determine
           POSIX compliance, falling back gracefully if commands
           fail.
        """
        task_vars = task_vars or {}
        tmp = None  # unused in modern Ansible

        result = super().run(tmp, task_vars)

        # Initialize result defaults
        result["is_posix"] = False
        result["compliance"] = {}

        # Test commands to check POSIX compliance - we try multiple
        # commands and see what works
        compliance = {}

        # Get POSIX versions in YAML format
        cmd = (
            'echo "POSIX1: $(getconf _POSIX_VERSION 2>/dev/null '
            '|| echo undefined)"; '
            'echo "POSIX2: $(getconf _POSIX2_VERSION 2>/dev/null '
            '|| echo undefined)"; '
            'echo "XOPEN_UNIX: $(getconf _XOPEN_UNIX 2>/dev/null '
            '|| echo undefined)"; '
            'echo "XOPEN_VERSION: $(getconf _XOPEN_VERSION 2>/dev/null '
            '|| echo undefined)"; '
            'echo "XOPEN_XCU_VERSION: $(getconf _XOPEN_XCU_VERSION '
            '2>/dev/null || echo undefined)"'
        )
        getconf_cmd = self._cmd(cmd, task_vars=task_vars, check_mode=False)

        if getconf_cmd.get("rc", 0) != 0:
            raise AnsibleActionFail(
                f"Failed to execute getconf commands: "
                f"{getconf_cmd.get('stderr', '')}"
            )

        # Parse the YAML-formatted output
        try:
            stdout = to_text(getconf_cmd.get("stdout", ""))
            values = yaml.safe_load(stdout)
            if not isinstance(values, dict):
                raise AnsibleActionFail(
                    f"getconf output did not parse as a dictionary: "
                    f"{stdout}"
                )
        except Exception as e:
            raise AnsibleActionFail(
                f"Failed to parse getconf output as YAML: {e}\n"
                f"Output: {getconf_cmd.get('stdout', '')}"
            )

        # Process POSIX.1 (XSH - System Interfaces and Headers)
        posix1_version = str(values.get("POSIX1", "undefined"))
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
            result["is_posix"] = True
        elif posix1_version not in ["undefined", "", "-1"]:
            self._display.warning(
                f"Unrecognized POSIX.1 version: {posix1_version}. "
                f"Known versions: {', '.join(self.POSIX_VERSIONS.keys())}"
            )

        # Process POSIX.2 (XCU - Shell and Utilities)
        posix2_version = str(values.get("POSIX2", "undefined"))
        xopen_xcu_version = str(values.get("XOPEN_XCU_VERSION", "undefined"))
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
                    f"({posix2_version})"
                )
            else:
                # POSIX2 was defined
                getconf_xcu["_POSIX2_VERSION"] = posix2_version
                # Include XCU_VERSION if it exists
                # (even if undefined)
                if xopen_xcu_version not in ["undefined", "", "-1"]:
                    getconf_xcu["_XOPEN_XCU_VERSION"] = xopen_xcu_version
                else:
                    getconf_xcu["_XOPEN_XCU_VERSION"] = None

            compliance["posix"]["components"]["xcu"]["version"][
                "getconf"
            ] = getconf_xcu

            result["is_posix"] = True
        elif posix2_version not in ["undefined", "", "-1"]:
            self._display.warning(
                f"Unrecognized POSIX.2 version: "
                f"{posix2_version}. "
                f"Known versions: {', '.join(self.POSIX_VERSIONS.keys())}"
            )

        try:
            # Process X/Open compliance
            xopen_support = str(values.get("XOPEN_UNIX", "undefined"))
            xopen_version = str(values.get("XOPEN_VERSION", "undefined"))

            # Add XSI indicator to POSIX components if
            # _XOPEN_UNIX > 0
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
                result["is_posix"] = True
            elif xopen_version not in ["undefined", "", "-1"]:
                self._display.warning(
                    f"Unrecognized X/Open version: {xopen_version}. "
                    f"Known versions: {', '.join(self.XOPEN_VERSIONS.keys())}"
                )
        except AnsibleConnectionFailure:
            raise
        except Exception as e:
            self._display.warning(f"Failed to process X/Open compliance: {e}")

        # Set final message
        if result.get("is_posix", False):
            if "sus" in compliance:
                # If SUS compliant, just mention SUS (it includes POSIX)
                result["msg"] = (
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
                    result["msg"] = (
                        f"System is POSIX-compliant ({', '.join(components)})"
                    )
                else:
                    result["msg"] = "System is POSIX-compliant"
            else:
                result["msg"] = "System is POSIX-compliant"
        else:
            result["msg"] = "The system is not POSIX compliant"

        # Add compliance to result
        result["compliance"] = compliance

        # Always return changed=False for test modules
        result["changed"] = False

        return result
