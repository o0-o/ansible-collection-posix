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


class ActionModule(PosixActionBase, ActionBase):
    """Collect specific environment variables from POSIX hosts.

    Runs ``set -eu; printf '%s' "$VAR"`` for each requested variable
    in parallel.  Unset variables produce a non-zero exit code (via
    ``set -u``) and are returned as ``None``.
    """

    TRANSFERS_FILES = False
    _requires_connection = True
    _supports_check_mode = True
    _supports_async = False
    _supports_diff = False

    def _build_commands(
        self,
        env_vars: list[str],
    ) -> dict[str, str]:
        """Build the command dict for parallel execution.

        :param list[str] env_vars: Environment variable names to
            collect
        :returns dict[str, str]: Mapping of variable names to shell
            commands
        """
        return {
            var: f"set -eu; printf '%s' \"${{{var}}}\"" for var in env_vars
        }

    def _parse_results(
        self,
        env_vars: list[str],
        run_results: dict[str, dict[str, Any]],
        wantlist: bool,
    ) -> Any:
        """Parse run results into the requested output format.

        :param list[str] env_vars: Original variable names (for
            ordering)
        :param dict[str, dict[str, Any]] run_results: Results from
            _run() keyed by variable name
        :param bool wantlist: Return list of single-key dicts when
            True
        :returns Any: Dict or list depending on wantlist
        """
        if wantlist:
            result = []
            for var in env_vars:
                cmd_result = run_results.get(var, {})
                value = (
                    None
                    if cmd_result.get("rc", 1) != 0
                    else cmd_result.get("stdout", "")
                )
                result.append({var: value})
            return result

        result = {}
        for var in env_vars:
            cmd_result = run_results.get(var, {})
            result[var] = (
                None
                if cmd_result.get("rc", 1) != 0
                else cmd_result.get("stdout", "")
            )
        return result

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
        }
        validation_result, new_args = self.validate_argument_spec(
            argument_spec=argument_spec
        )
        result["invocation"] = self._task.args.copy()

        env_vars = new_args["env"]
        wantlist = new_args.get("wantlist", False)

        # Build and execute commands in parallel
        commands = self._build_commands(env_vars)

        self._display.vvv(
            f"Collecting {len(env_vars)} environment variable(s): "
            f"{', '.join(env_vars)}"
        )

        run_results = self._run(
            commands,
            parallel=True,
            fail_fast=False,
            task_vars=task_vars,
            check_mode=False,
        )

        # Parse results
        env_data = self._parse_results(env_vars, run_results, wantlist)

        result.update(
            {
                "changed": False,
                "env": env_data,
                "msg": (
                    f"Collected {len(env_vars)} environment" f" variable(s)"
                ),
            }
        )

        return result
