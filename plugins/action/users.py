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

from ansible.errors import AnsibleActionFail
from ansible.plugins.action import ActionBase

from ansible_collections.o0_o.posix.plugins.module_utils import (
    ReadPosixActionBase,
    batch_read,
    compose_homes,
    compose_paths,
    compose_shell_files,
    compose_users_groups,
    parse_shells,
)


class ActionModule(ReadPosixActionBase, ActionBase):
    """Gather user and group information from POSIX hosts."""

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
        """Execute user and group fact gathering.

        :param Optional[str] tmp: Unused temporary directory path
        :param Optional[dict[str, Any]] task_vars: Available Ansible
            variables
        :returns dict[str, Any]: Result dictionary with o0_users,
            o0_groups, o0_shell_files, and o0_paths data
        """
        task_vars = task_vars or {}
        self._def_inventory_hostname(task_vars)

        result = super().run(tmp, task_vars=task_vars)
        del tmp  # unused

        argument_spec = {
            "passwd_path": {
                "type": "str",
                "default": "/etc/passwd",
                "no_log": False,
            },
            "group_path": {"type": "str", "default": "/etc/group"},
            "shells_path": {"type": "str", "default": "/etc/shells"},
        }

        validation_result, module_args = self.validate_argument_spec(
            argument_spec=argument_spec
        )
        self._task.args.update(module_args)

        passwd_path = module_args["passwd_path"]
        group_path = module_args["group_path"]
        shells_path = module_args["shells_path"]

        users, groups = compose_users_groups(
            self._read_text_file(passwd_path, task_vars),
            self._read_text_file(group_path, task_vars),
        )

        def read_paths(paths: list[str]) -> dict[str, Any]:
            return self._read(paths=paths, task_vars=task_vars)

        # Homes and shell files are both metadata reads over paths the
        # passwd entries already named, so they are read together
        known_shell_files = task_vars.get("o0_shell_files")
        read = batch_read(users, read_paths, known_shell_files)

        result.update(
            {
                "changed": False,
                "o0_users": users,
                "o0_groups": groups,
                "o0_shell_files": compose_shell_files(
                    users, read, known_shell_files
                ),
            }
        )

        # A home is a path, so it is an entry of the one flat path
        # store: tagged home, carrying the UIDs that live there, and
        # composed in beside everything else the module observed
        # rather than published as a namespace of its own.
        paths = compose_paths(None, compose_homes(users, read))

        # A single file parsed on its own lands at its own path: the
        # bytes under content, the login shells they name under
        # config. Not every host names its login shells, and a host
        # whose file could not be read leaves the path unmentioned
        # rather than empty, which would read as a host that names
        # none.
        shells = self._read_text_file(shells_path, task_vars, required=False)
        if shells is not None:
            paths = compose_paths(
                paths,
                {
                    shells_path: {
                        "content": shells,
                        "config": parse_shells(shells),
                    }
                },
            )

        if paths:
            result["o0_paths"] = paths

        return result

    def _read_text_file(
        self,
        path: str,
        task_vars: dict[str, Any],
        required: bool = True,
    ) -> Optional[str]:
        cmd_result = self._command(
            ["cat", path], task_vars=task_vars, check_mode=False
        )
        if cmd_result.get("rc") != 0:
            if not required:
                return None
            error_msg = cmd_result.get("stderr") or cmd_result.get("stdout")
            raise AnsibleActionFail(f"Failed to read {path}: {error_msg}")
        return cmd_result.get("stdout", "")
