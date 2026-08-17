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

from ansible_collections.o0_o.posix.plugins.module_utils import PosixActionBase


class ActionModule(PosixActionBase, ActionBase):
    """Resolve a command's full path on POSIX systems.

    Clears aliases, prefers ``command -v`` and falls back to ``which``.
    Always executes in a POSIX shell to support ``unalias -a``.
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
        task_vars = task_vars or {}
        self._def_inventory_hostname(task_vars)

        result = super().run(tmp, task_vars=task_vars)
        del tmp  # unused

        # Validate args
        argument_spec = {
            "command": {"type": "str", "required": True},
        }
        validation_result, new_args = self.validate_argument_spec(
            argument_spec=argument_spec
        )
        command = new_args["command"]

        path = self._which(command, task_vars=task_vars)

        result.update({"changed": False, "path": path or None})
        return result
