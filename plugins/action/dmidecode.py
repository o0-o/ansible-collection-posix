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
        task_vars = task_vars or {}
        tmp = None

        result = super().run(tmp, task_vars)

        # Validate args (no arguments needed)
        argument_spec = {}
        validation_result, new_args = self.validate_argument_spec(
            argument_spec=argument_spec
        )

        # Execute dmidecode command
        cmd_result = self._cmd(
            ["dmidecode"], task_vars=task_vars, check_mode=False
        )

        if cmd_result.get("rc") != 0:
            stderr = cmd_result.get("stderr", "")
            stdout = cmd_result.get("stdout", "")
            error_msg = stderr or stdout or "Unknown error"
            raise AnsibleActionFail(f"dmidecode command failed: {error_msg}")

        # Parse the output using the dmidecode filter
        try:
            hardware = dmidecode(cmd_result.get("stdout", ""))
        except (ValueError, ImportError) as e:
            raise AnsibleActionFail(
                f"Failed to parse dmidecode output: {type(e).__name__}: {e}"
            ) from e

        result.update({"changed": False, "hardware": hardware})
        return result
