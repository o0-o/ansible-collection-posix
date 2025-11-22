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
)


class ActionModule(ReadPosixActionBase, ActionBase):
    """Gather file metadata using POSIX stat command and jc parser.

    This action plugin provides portable file metadata gathering using
    the stat command with jc parsing. Uses multi-stage command batching
    for efficiency, minimizing SSH round trips.

    Implementation notes:
    - Timestamps have second precision only (not millisecond)
    - The 'version' field is not available (requires ioctl/statx)
    - The 'generation' field is not available on Linux
      (requires ioctl, BSD/macOS may support via stat -f %v)
    - Compatible with ansible.builtin.stat return structure
    """

    TRANSFERS_FILES = False
    _requires_connection = True
    _supports_check_mode = True
    _supports_async = False

    def run(
        self,
        tmp: Optional[str] = None,
        task_vars: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """Execute stat and return file metadata.

        :param Optional[str] tmp: Unused temporary directory path
        :param Optional[dict[str, Any]] task_vars: Available Ansible
            variables
        :returns dict[str, Any]: Result with file metadata under 'stat'
            key
        :raises AnsibleActionFail: When invalid arguments are provided
        """
        task_vars = task_vars or {}
        self._def_inventory_hostname(task_vars)

        result = super().run(tmp, task_vars)
        del tmp  # unused

        result["invocation"] = self._task.args.copy()
        result["changed"] = False

        argument_spec = {
            "path": {
                "type": "str",
                "required": True,
                "aliases": ["dest", "name"],
            },
            "follow": {"type": "bool", "default": False},
            "get_checksum": {"type": "bool", "default": True},
            "get_mime": {
                "type": "bool",
                "default": True,
                "aliases": ["mime", "mime_type"],
            },
            "get_attributes": {
                "type": "bool",
                "default": True,
                "aliases": ["attr", "attributes"],
            },
            "checksum_algorithm": {
                "type": "str",
                "default": "sha1",
                "choices": [
                    "md5",
                    "sha1",
                    "sha224",
                    "sha256",
                    "sha384",
                    "sha512",
                ],
                "aliases": ["checksum", "checksum_algo"],
            },
            "_force_raw": {"type": "bool", "default": False},
        }
        validation_result, new_args = self.validate_argument_spec(
            argument_spec=argument_spec
        )

        # Extract arguments
        path = new_args["path"]
        follow = new_args["follow"]
        get_checksum = new_args["get_checksum"]
        get_mime = new_args["get_mime"]
        get_attributes = new_args["get_attributes"]
        checksum_algorithm = new_args["checksum_algorithm"]
        force_raw = new_args["_force_raw"]

        # === STAGE 1: Initial discovery ===
        # Get stage 1 commands from mixin
        stage1_commands = self._get_stat_commands_stage1(path, get_mime)

        # Execute stage 1 (using dict mode for automatic keying)
        stage1_result = self._run(
            commands=dict(stage1_commands),
            force_raw=force_raw,
            task_vars=task_vars,
            check_mode=False,
        )

        # Note: Don't check stage1_result.get("failed") because some commands
        # are expected to fail (e.g., readlink on non-symlinks). The
        # processing methods will handle missing data appropriately.

        # Get raw flag from run result
        result["raw"] = stage1_result.get("raw", False)

        # Dict mode returns results already keyed by tag
        stage1_tagged_results = stage1_result["commands"]

        # Process stage 1
        try:
            partial_stat, stage2_params = self._process_stat_stage1(
                stage1_tagged_results, path, follow
            )
        except (ValueError, RuntimeError) as e:
            raise AnsibleActionFail(str(e)) from e

        # Early return if file doesn't exist
        if not partial_stat.get("exists"):
            result["stat"] = partial_stat
            return result

        # === STAGE 2: Conditional commands based on stage 1 ===
        # Get stage 2 commands from mixin
        stage2_commands = self._get_stat_commands_stage2(
            path=path,
            username=stage2_params["username"],
            groupname=stage2_params["groupname"],
            is_symlink=stage2_params["is_symlink"],
            follow=follow,
            file_type_char=stage2_params["file_type_char"],
            is_regular_file=stage2_params["is_regular_file"],
            get_checksum=get_checksum,
            checksum_algorithm=checksum_algorithm,
            get_attributes=get_attributes,
        )

        # Execute stage 2 (using dict mode for automatic keying)
        stage2_result = self._run(
            commands=dict(stage2_commands),
            force_raw=force_raw,
            task_vars=task_vars,
            check_mode=False,
        )

        # Note: Don't check stage2_result.get("failed") because some commands
        # are expected to fail (e.g., checksum commands on systems without
        # those tools). The processing methods will handle missing data.

        # Dict mode returns results already keyed by tag
        stage2_tagged_results = stage2_result["commands"]

        # === FINAL PROCESSING ===
        # Process stage 2 and finalize stat
        try:
            stat_result = self._process_stat_stage2(
                tagged_results=stage2_tagged_results,
                stage1_tagged_results=stage1_tagged_results,
                partial_stat=partial_stat,
                stage2_params=stage2_params,
                path=path,
                get_checksum=get_checksum,
                checksum_algorithm=checksum_algorithm,
                get_mime=get_mime,
                get_attributes=get_attributes,
                task_vars=task_vars,
            )
        except (ValueError, RuntimeError) as e:
            raise AnsibleActionFail(str(e)) from e

        result["stat"] = stat_result
        return result
