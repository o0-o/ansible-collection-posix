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
    get_getconf_command_requests,
    process_getconf_command_results,
)


class ActionModule(PosixActionBase, ActionBase):
    """Ask the host what its own configuration limits are.

    One ``getconf`` per variable IEEE Std 1003.1 names, in a single
    batch, composed by the same processor the facts module's
    ``config`` subset uses - so the standalone module and the gather
    publish one shape under one name and cannot disagree about it.

    The variables are the fact rather than evidence for one, so the
    namespace names the command that asked and nothing more: a fact is
    not evidence for itself.
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
        """Ask the host for its configuration variables.

        :param Optional[str] tmp: Unused temporary directory path
        :param Optional[dict[str, Any]] task_vars: Available Ansible
            variables
        :returns dict[str, Any]: Result with the variables under
            'config', and ansible_facts where gather was asked for
        """
        task_vars = task_vars or {}
        self._def_inventory_hostname(task_vars)

        result = super().run(tmp, task_vars=task_vars)
        del tmp  # unused

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

        cmds = get_getconf_command_requests()

        run_results = self._run(
            cmds,
            parallel=True,
            fail_fast=False,
            task_vars=task_vars,
            # A getconf changes nothing, and a check mode run that
            # skipped it would read as a host that answers nothing
            check_mode=False,
        )

        facts, errors = process_getconf_command_results(run_results)

        for err in errors:
            self._display.warning(f"[{self.inventory_hostname}] {err}")

        namespace = facts.get("o0_os") or {}

        result.update(
            {
                "changed": False,
                # A host whose getconf refused every variable leaves
                # the answer empty rather than absent here: the module
                # was asked and this is what it got
                "config": namespace.get("config") or {},
                "evidence": namespace.get("evidence") or {},
            }
        )

        if new_args.get("gather", False) and facts:
            result["ansible_facts"] = facts

        return result
