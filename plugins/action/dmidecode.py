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

from typing import Any, Dict, Optional

from ansible.errors import AnsibleActionFail
from ansible.plugins.action import ActionBase

from ansible_collections.o0_o.posix.plugins.module_utils import (
    PosixActionBase,
    dmidecode,
)


class ActionModule(PosixActionBase, ActionBase):
    """Gather hardware information using dmidecode.

    Executes dmidecode command and parses output into structured format.
    """

    TRANSFERS_FILES = False
    _requires_connection = True
    _supports_check_mode = True
    _supports_async = False
    _supports_diff = False

    def run(
        self,
        tmp: Optional[str] = None,
        task_vars: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Main entry point for the action plugin.

        Executes dmidecode command and parses output into structured
        hardware information. Requires root privileges on most systems.

        :param Optional[str] tmp: Temporary directory path (unused)
        :param Optional[Dict[str, Any]] task_vars: Task variables
        :returns Dict[str, Any]: Result with hardware information
        """
        task_vars = task_vars or {}
        self._def_inventory_hostname(task_vars)

        result = super(ActionModule, self).run(tmp, task_vars=task_vars)
        result["changed"] = False
        del tmp  # unused

        # Validate args (no arguments needed)
        argument_spec = {}
        validation_result, new_module_args = self.validate_argument_spec(
            argument_spec=argument_spec
        )

        # Execute dmidecode command
        cmd_result = self._cmd(
            ["dmidecode"], task_vars=task_vars, check_mode=False
        )

        if cmd_result.get("rc") != 0:
            stderr = cmd_result.get("stderr", "")
            stdout = cmd_result.get("stdout", "")
            rc = cmd_result.get("rc")
            error_msg = stderr or stdout or "Unknown error"
            result.update(
                {
                    "failed": True,
                    "msg": (
                        f"dmidecode command failed with code {rc}: {error_msg}"
                    ),
                    "hardware": {},
                }
            )
            return result

        # Parse the output using the dmidecode filter
        try:
            hardware = dmidecode(cmd_result.get("stdout", ""))
        except (ValueError, ImportError) as e:
            raise AnsibleActionFail(
                f"Failed to parse dmidecode output: {type(e).__name__}: {e}"
            ) from e

        result["hardware"] = hardware

        return result
