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

from typing import Any, Optional

from ansible.plugins.action import ActionBase

from ansible_collections.o0_o.utils.plugins.module_utils.typeguard_compat import (  # noqa: E501
    typechecked,
)

from ansible_collections.o0_o.core.plugins.module_utils import (
    name_origins,
)
from ansible_collections.o0_o.posix.plugins.module_utils import (
    PosixActionBase,
    compose_paths,
    get_compliance_command_requests,
    missing_commands,
    process_all_compliance_command_results,
)

# What this module is called, which is what a path entry names as
# having contributed it
FQCN = "o0_o.posix.compliance"


class ActionModule(PosixActionBase, ActionBase):
    """Check POSIX and UNIX standards compliance of the target host.

    This action plugin checks the standards compliance of the target
    system by querying POSIX, X/Open, and SUS compliance information
    using getconf commands. It gracefully handles systems that may not
    have getconf or may not be standards-compliant.

    The module returns detailed compliance information for POSIX
    (XSH/XCU), SUS, and XSI when available. Use the 'posix' Jinja2 test
    to check if the system is POSIX-compliant based on the returned
    compliance data.
    """

    TRANSFERS_FILES = False
    _requires_connection = True
    _supports_check_mode = True
    _supports_async = False
    _supports_diff = False

    @typechecked
    def _format_compliance_message(self, result: dict[str, Any]) -> str:
        """Format a human-readable compliance status message.

        :param dict[str, Any] result: Result dict containing 'compliance' key
        :returns str: Human-readable status message
        """
        compliance = result.get("compliance", {})

        sus = compliance.get("sus", {})
        if sus.get("supported") is True:
            version = sus.get("version", {}).get("pretty", "")
            if version:
                return f"System is SUS-compliant ({version})"
            return "System is SUS-compliant"

        posix = compliance.get("posix", {})
        posix_support = posix.get("supported")
        if posix_support is True:
            components = []
            for key in ("xsh", "xcu", "xsi"):
                if compliance.get(key, {}).get("supported") is True:
                    components.append(key.upper())
            if components:
                return f"System is POSIX-compliant ({', '.join(components)})"
            return "System is POSIX-compliant"
        elif posix_support == "partial":
            components = []
            for key in ("xsh", "xcu"):
                if compliance.get(key, {}).get("supported") is True:
                    components.append(key.upper())
            if components:
                parts = ", ".join(components)
                return f"System is partially POSIX-compliant ({parts})"
            return "System is partially POSIX-compliant"

        return "System is not POSIX-compliant"

    def run(
        self,
        tmp: Optional[str] = None,
        task_vars: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """Main entry point for the action plugin.

        Tests if the target system is POSIX-compliant by checking for
        POSIX version information using getconf commands. Uses batched
        parallel execution via the run action plugin for efficiency.

        :param Optional[str] tmp: Temporary directory path (unused)
        :param Optional[dict[str, Any]] task_vars: Task variables
        :returns dict[str, Any]: Result with compliance information
        """
        task_vars = task_vars or {}
        self._def_inventory_hostname(task_vars)

        result = super().run(task_vars=task_vars)
        del tmp  # unused

        # Validate arguments
        argument_spec = {
            "gather": {
                "type": "bool",
                "default": False,
            },
        }
        validation_result, new_args = self.validate_argument_spec(
            argument_spec=argument_spec
        )
        result["invocation"] = self._task.args.copy()

        gather = new_args.get("gather", False)

        # Get command requests for compliance checks
        cmds = get_compliance_command_requests()

        # Execute all commands in parallel via run plugin (using dict mode)
        commands_result = self._run(
            cmds,
            parallel=True,
            fail_fast=False,
            task_vars=task_vars,
            check_mode=False,  # Always run getconf even in check mode
        )

        # Process results into compliance structure. The processor
        # names the facts; the module's own returns are the same
        # values unwrapped, plus the missing list derived from the
        # standards that already record it.
        facts, errors = process_all_compliance_command_results(commands_result)
        compliance = facts["o0_os"]["compliance"]
        # The processor composes on this module's behalf, so this is
        # where the entries learn whose observation they are
        facts["o0_paths"] = compose_paths(None, facts["o0_paths"], origin=FQCN)
        name_origins(facts, FQCN)
        result.update(
            {
                "compliance": compliance,
                "paths": facts["o0_paths"],
                "shells": facts["o0_shells"],
                "missing_commands": missing_commands(compliance),
            }
        )

        # Emit any errors
        for err in errors:
            self._display.warning(f"[{self.inventory_hostname}] {err}")

        # Format message
        result["msg"] = self._format_compliance_message(result)

        # Set ansible_facts when gather is enabled
        if gather:
            result["ansible_facts"] = facts

        result["changed"] = False

        return result
