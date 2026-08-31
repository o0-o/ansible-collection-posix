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
    compose_paths,
    get_effective_uid_command_requests,
    process_effective_uid_results,
)

# What this module is called, which is what a path entry names as
# having contributed it
FQCN = "o0_o.posix.which"


class ActionModule(PosixActionBase, ActionBase):
    """Resolve a command's full path on POSIX systems.

    Clears aliases, prefers ``command -v`` and falls back to ``which``.
    Always executes in a POSIX shell to support ``unalias -a``.

    A resolution is a fact about the file it landed on, so it is also
    answered as an o0_paths observation keyed by that path, the same
    store a compliance sweep fills.  What the lookup found is what the
    shell running it would run, so the executable claim is keyed by
    the uid that shell was running as, which the module asks for.
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

        # A builtin answers with its own name and names no file, and a
        # single lookup that missed names no path it was not at, so
        # both leave the store unmentioned rather than guessed at.
        if path and path.startswith("/"):
            uid = process_effective_uid_results(
                self._run(
                    get_effective_uid_command_requests(),
                    task_vars=task_vars,
                    check_mode=False,
                )
                or []
            )
            # A row is one uid's answer. Where the host would not say
            # whose answer this is, the path is still what the command
            # resolved to and the claim is what has to be left out
            observation: dict[str, Any] = {path: {}}
            if uid is not None:
                observation[path] = {"executable": {str(uid): True}}
            try:
                result["o0_paths"] = compose_paths(
                    None, observation, origin=FQCN
                )
            except ValueError as exc:
                self._display.warning(f"[{self.inventory_hostname}] {exc}")

        return result
