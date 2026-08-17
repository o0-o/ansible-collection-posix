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

from datetime import datetime
from typing import Any, Optional

from ansible.errors import AnsibleActionFail
from ansible.plugins.action import ActionBase

from ansible_collections.o0_o.posix.plugins.module_utils import (
    PosixActionBase,
    parse_uptime,
)


class ActionModule(PosixActionBase, ActionBase):
    """Gather uptime information using the POSIX uptime command."""

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
        """Execute uptime fact gathering.

        :param Optional[str] tmp: Unused temporary directory path
        :param Optional[dict[str, Any]] task_vars: Available Ansible
            variables
        :returns dict[str, Any]: Result dictionary with parsed uptime
            data
        """
        task_vars = task_vars or {}
        self._def_inventory_hostname(task_vars)

        result = super().run(tmp, task_vars=task_vars)
        del tmp  # unused

        # Get target system timezone to calculate boot time correctly
        target_tz = self._get_target_timezone(task_vars)
        reference_time = datetime.now(target_tz)

        cmd_result = self._command(["uptime"], task_vars=task_vars)
        if cmd_result.get("rc", 0) != 0:
            stderr = cmd_result.get("stderr", "").strip()
            raise AnsibleActionFail(f"uptime command failed: {stderr}")

        try:
            parsed = parse_uptime(cmd_result, now=reference_time)
        except Exception as exc:
            raise AnsibleActionFail(
                f"Failed to parse uptime output: {exc}"
            ) from exc

        result.update(
            {
                "changed": False,
                "uptime": parsed["uptime"],
                "load": parsed["load"],
                "login_sessions": parsed.get("login_sessions", 0),
            }
        )
        return result
