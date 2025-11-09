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
    ReadPosixActionBase,
)


class ActionModule(ReadPosixActionBase, ActionBase):
    """Gather file metadata using stat with jc fallback.

    This action plugin provides file metadata gathering that
    automatically falls back to parsing stat command output with jc
    when Python is not available on the remote host.

    Raw mode limitations (when _force_raw=true or Python unavailable):
    - Timestamps have second precision only (not millisecond)
    - The 'version' field is not available (requires ioctl/statx)
    - The 'generation' field is not available on Linux
      (requires ioctl, BSD/macOS may support via stat -f %v)
    """

    TRANSFERS_FILES = False
    _requires_connection = True
    _supports_check_mode = True
    _supports_async = False

    def run(
        self,
        tmp: Optional[str] = None,
        task_vars: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Execute stat and return file metadata.

        :param Optional[str] tmp: Unused temporary directory path
        :param Optional[Dict[str, Any]] task_vars: Available Ansible
            variables
        :returns Dict[str, Any]: Result with file metadata under 'stat'
            key
        :raises AnsibleActionFail: When invalid arguments are provided
        """
        task_vars = task_vars or {}
        tmp = None

        result = super().run(tmp, task_vars)
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
        validation_result, new_module_args = self.validate_argument_spec(
            argument_spec=argument_spec
        )
        self.force_raw = new_module_args.pop("_force_raw")

        # Try ansible.builtin.stat first
        if not self.force_raw:
            builtin_module_args = new_module_args.copy()
            ansible_stat_mod = self._execute_module(
                module_name="ansible.builtin.stat",
                module_args=builtin_module_args,
                task_vars=task_vars,
            )
            ansible_stat_mod.pop("invocation", None)

            if not self._is_interpreter_missing(ansible_stat_mod):
                result.update(ansible_stat_mod)
                result["raw"] = False
            else:
                host = self._get_inventory_hostname(task_vars)
                self._display.warning(
                    f"[{host}] Ansible command module failed; "
                    "falling back to raw command."
                )
                self.force_raw = True

        if self.force_raw:
            # Fall back to stat command with jc
            result = {
                "changed": False,
                "raw": True,
            }
            try:
                result["stat"] = self._stat_with_jc(
                    new_module_args, task_vars=task_vars
                )
            except (ValueError, RuntimeError) as e:
                raise AnsibleActionFail(str(e))

        self._remove_tmp_path(self._connection._shell.tmpdir)

        return result
