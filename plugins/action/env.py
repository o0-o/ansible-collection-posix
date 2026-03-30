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
from ansible_collections.o0_o.posix.plugins.module_utils.env_utils import (
    get_env_command_requests,
    process_env_command_results,
)


class ActionModule(PosixActionBase, ActionBase):
    """Collect specific environment variables from POSIX hosts.

    Uses the COMMAND_SPEC pattern to run
    ``set -eu; printf '%s' "$VAR"`` for each requested variable
    in parallel.  Unset variables produce a non-zero exit code
    (via ``set -u``) and are returned as ``None``.
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
        """Execute environment variable collection.

        :param Optional[str] tmp: Unused temporary directory path
        :param Optional[dict[str, Any]] task_vars: Available Ansible
            variables
        :returns dict[str, Any]: Result dictionary with collected
            env vars
        """
        task_vars = task_vars or {}
        self._def_inventory_hostname(task_vars)

        result = super().run(tmp, task_vars=task_vars)
        del tmp  # unused

        # Validate arguments
        argument_spec = {
            "env": {
                "type": "list",
                "elements": "str",
                "required": True,
            },
            "wantlist": {
                "type": "bool",
                "default": False,
            },
            "undefined": {
                "type": "str",
                "choices": ["exclude", "null"],
                "default": "exclude",
            },
        }
        validation_result, new_args = self.validate_argument_spec(
            argument_spec=argument_spec
        )
        result["invocation"] = self._task.args.copy()

        env_vars = new_args["env"]
        wantlist = new_args.get("wantlist", False)
        include_undefined = new_args.get("undefined") == "null"

        self._display.vvv(
            f"Collecting {len(env_vars)} environment"
            f" variable(s): {', '.join(env_vars)}"
        )

        # Build and execute via COMMAND_SPEC
        cmds = get_env_command_requests(env_vars)

        run_results = self._run(
            cmds,
            parallel=True,
            fail_fast=False,
            task_vars=task_vars,
            check_mode=False,
        )

        # Process results
        env_data = process_env_command_results(
            run_results, env_vars, wantlist, include_undefined
        )

        result.update(
            {
                "changed": False,
                "env": env_data,
                "msg": (
                    f"Collected {len(env_vars)}" f" environment variable(s)"
                ),
            }
        )

        return result
