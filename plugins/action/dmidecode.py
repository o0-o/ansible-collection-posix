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
    get_dmidecode_command_requests,
    process_dmidecode_command_results,
)


class ActionModule(PosixActionBase, ActionBase):
    """Gather hardware information using dmidecode.

    Uses the COMMAND_SPEC pattern to run ``dmidecode`` via batched
    ``_run()`` execution and parse the result into structured
    hardware data.
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
        """Execute dmidecode and return structured hardware data.

        :param Optional[str] tmp: Unused temporary directory path
        :param Optional[dict[str, Any]] task_vars: Available Ansible
            variables
        :returns dict[str, Any]: Result with hardware data under
            'hardware' key
        """
        task_vars = task_vars or {}
        self._def_inventory_hostname(task_vars)

        result = super().run(tmp, task_vars=task_vars)
        del tmp  # unused

        cmds = get_dmidecode_command_requests()

        run_results = self._run(
            cmds,
            parallel=True,
            fail_fast=False,
            task_vars=task_vars,
            check_mode=False,
        )

        facts, errors = process_dmidecode_command_results(run_results)

        for err in errors:
            self._display.warning(f"[{self.inventory_hostname}] {err}")

        result.update(
            {
                "changed": False,
                "hardware": facts.get("o0_hardware", {}),
            }
        )

        return result
