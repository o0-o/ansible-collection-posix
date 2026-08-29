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
    get_file_command_requests,
    parse_shells,
    process_file_command_results,
)


class ActionModule(ReadPosixActionBase, ActionBase):
    """Gather user and group information from POSIX hosts.

    Two round trips: one batch reads the files users are named in,
    and one metadata read describes the paths those files named.
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

        # Three files, one round trip: a read is a command like any
        # other, so the reads travel together the way a gather's do
        files = self._read_files(
            [passwd_path, group_path, shells_path], task_vars
        )

        users, groups = compose_users_groups(
            self._content(files, passwd_path),
            self._content(files, group_path),
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
        shells = self._content(files, shells_path, required=False)
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

    def _read_files(
        self,
        paths: list[str],
        task_vars: dict[str, Any],
    ) -> dict[str, dict[str, Any]]:
        """Read the named files in a single round trip.

        The module gathers facts from hosts that have no Python, so a
        file a fact is read from is read the way every other fact is
        gathered: a batched command with the raw fallback under it,
        never slurp.

        :param list[str] paths: Paths to read
        :param dict[str, Any] task_vars: Task variables
        :returns dict[str, dict[str, Any]]: What the batch learned
            about each path, keyed by path
        """
        return process_file_command_results(
            self._run(
                get_file_command_requests(paths),
                parallel=True,
                fail_fast=False,
                task_vars=task_vars,
                check_mode=False,
            )
        )

    def _content(
        self,
        files: dict[str, dict[str, Any]],
        path: str,
        required: bool = True,
    ) -> Optional[str]:
        """The bytes one of the batched reads answered with.

        A file the module cannot compose a fact without is required,
        and a read of it that failed fails the task rather than
        publishing a shape short a half.  A file the host need not
        have is not, and reads None so the fact it feeds is left
        unmentioned.

        :param dict[str, dict[str, Any]] files: What the batch learned
        :param str path: The path whose content is wanted
        :param bool required: Whether a failed read fails the task
        :returns Optional[str]: The content, or None where a file that
            was not required did not answer
        :raises AnsibleActionFail: If a required file did not answer
        """
        result = files.get(path) or {}
        content = result.get("parsed")

        if content is None and required:
            error = result.get("stderr") or result.get("stdout")
            raise AnsibleActionFail(f"Failed to read {path}: {error}")

        return content
