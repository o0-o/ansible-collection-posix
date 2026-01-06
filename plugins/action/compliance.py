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

from ansible_collections.o0_o.posix.plugins.module_utils import (
    PosixActionBase,
)
from ansible_collections.o0_o.posix.plugins.module_utils.compliance import (
    format_compliance_message,
    get_compliance_commands,
    process_compliance_results,
)


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

        # Get tagged commands for compliance checks
        commands = get_compliance_commands()

        # Execute all commands in parallel via run plugin (using dict mode)
        run_result = self._run(
            commands,
            parallel=True,
            fail_fast=False,
            task_vars=task_vars,
            check_mode=False,  # Always run getconf even in check mode
        )

        # Dict mode returns results already keyed by tag
        commands_results = run_result["commands"]

        # Process results into compliance structure
        compliance, errors, debug_msgs = process_compliance_results(
            commands_results
        )

        # Emit any errors or debug messages
        for msg in debug_msgs:
            self._display.vvv(msg)
        for err in errors:
            self._display.warning(f"[{self.inventory_hostname}] {err}")

        # Format message
        result["msg"] = format_compliance_message(compliance)
        result["compliance"] = compliance
        result["changed"] = False

        return result
