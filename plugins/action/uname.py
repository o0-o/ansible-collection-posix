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
from ansible_collections.o0_o.posix.plugins.module_utils.uname_utils import (
    get_uname_command_requests,
    process_uname_command_results,
)


class ActionModule(PosixActionBase, ActionBase):
    """Gather kernel, hostname, and architecture from uname.

    Uses the COMMAND_SPEC pattern to run ``uname -a`` via batched
    ``_run()`` execution and parse the result into structured data.
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
        """Execute uname fact gathering.

        :param Optional[str] tmp: Unused temporary directory path
        :param Optional[dict[str, Any]] task_vars: Available Ansible
            variables
        :returns dict[str, Any]: Result dictionary with parsed uname
            data
        """
        task_vars = task_vars or {}
        self._def_inventory_hostname(task_vars)

        result = super().run(tmp, task_vars=task_vars)
        del tmp  # unused

        cmds = get_uname_command_requests()

        run_results = self._run(
            cmds,
            parallel=True,
            fail_fast=False,
            task_vars=task_vars,
            check_mode=False,
        )

        facts, errors = process_uname_command_results(run_results)

        for err in errors:
            self._display.warning(f"[{self.inventory_hostname}] {err}")

        # Flatten namespace structure into uname key
        uname_data = {}
        for ns_facts in facts.values():
            for key, value in ns_facts.items():
                uname_data[key] = value

        result.update(
            {
                "changed": False,
                "uname": uname_data,
                "msg": "Gathered uname facts",
            }
        )

        return result
