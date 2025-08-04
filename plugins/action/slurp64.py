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

from base64 import b64decode
from typing import Any, Dict, Optional

from ansible.errors import AnsibleActionFail
from ansible_collections.o0_o.posix.plugins.action_utils import PosixBase


class ActionModule(PosixBase):
    """
    Read file contents from remote hosts with raw fallback support.

    This action plugin reads file contents from remote hosts using the
    standard Ansible slurp module, automatically falling back to raw
    'cat' execution when Python interpreter is unavailable on the
    remote host.

    The plugin decodes base64 content returned by the slurp module
    and provides UTF-8 decoded content in the 'content' key, along
    with 'content_lines' for convenient line-by-line access.

    .. note::
       This plugin does not transfer files but requires a connection
       to read from remote hosts. It supports both native slurp and
       raw cat fallback modes.
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
        """
        Read file contents from remote host with raw fallback.

        Attempts to read file contents using the standard Ansible slurp
        module first, then falls back to raw 'cat' execution if Python
        interpreter is missing on the remote host.

        :param Optional[str] tmp: Temporary directory path (unused in
            modern Ansible)
        :param Optional[Dict[str, Any]] task_vars: Task variables
            dictionary
        :returns Dict[str, Any]: Standard Ansible result dictionary

        :raises AnsibleActionFail: When file reading fails, base64
            decoding fails, or required parameters are missing

        .. note::
           This method validates the 'src' parameter and supports
           '_force_raw' to bypass native slurp module usage.
        """
        task_vars = task_vars or {}

        self._display.vvv("slurp64: starting run()")

        # Define the expected input parameters
        argument_spec = {
            "src": {"type": "str", "required": True},
            "_force_raw": {"type": "bool", "default": False},
        }

        # Validate input against spec and extract usable values
        validation_result, new_module_args = self.validate_argument_spec(
            argument_spec=argument_spec
        )
        src = new_module_args.get("src")
        self.force_raw = new_module_args.pop("_force_raw")

        self._display.vvv(f"slurp64: parsed src={src}, _force_raw={self.force_raw}")

        # Initialize the result structure from the base Action class
        result = super().run(tmp, task_vars)
        result["invocation"] = self._task.args.copy()
        result["msg"] = ""
        del tmp

        if self.force_raw:
            self._display.vvv("slurp64: forcing raw mode, calling _cat()")
            cat_result = self._cat(src, task_vars=task_vars)
            self._display.vvv(f"slurp64: _cat() returned {cat_result}")
            result.update(cat_result)
            result["raw"] = True
        else:
            self._display.vvv("slurp64: attempting ansible.builtin.slurp")

            try:
                ansible_slurp_mod = self._execute_module(
                    module_name="ansible.builtin.slurp",
                    module_args={"src": src},
                    task_vars=task_vars,
                )
                self._display.vvv(f"slurp64: builtin slurp: {ansible_slurp_mod}")
                ansible_slurp_mod.pop("invocation")
                result["raw"] = False
            except Exception as e:
                self._display.warning(f"Error calling ansible.builtin.slurp: {str(e)}")
                ansible_slurp_mod = {
                    "failed": True,
                    "rc": 127,
                    "module_stderr": str(e),
                }

            if self._is_interpreter_missing(ansible_slurp_mod):
                self._display.warning(
                    "Ansible slurp module failed on host "
                    f"{task_vars.get('inventory_hostname', 'UNKNOWN')}, "
                    "falling back to raw 'cat'."
                )
                self._display.vvv(
                    "slurp64: falling back to _cat() due to interpreter error"
                )
                cat_result = self._cat(src, task_vars=task_vars)
                self._display.vvv(f"slurp64: _cat() fallback returned {cat_result}")
                result.update(cat_result)
                result["raw"] = True
            else:
                if "content" in ansible_slurp_mod:
                    self._display.vvv("slurp64: decoding slurp content")
                    try:
                        ansible_slurp_mod.pop("encoding", None)
                        ansible_slurp_mod["content"] = b64decode(
                            ansible_slurp_mod["content"]
                        ).decode("utf-8")
                        self._display.vvv("slurp64: decode succeeded")
                    except Exception as decode_error:
                        raise AnsibleActionFail(
                            "Failed to base64 decode slurp content: " f"{decode_error}"
                        )

                else:
                    self._display.warning(
                        "slurp64: builtin slurp did not return 'content'"
                    )

                result.update(ansible_slurp_mod)

        if "content" in result:
            result["content_lines"] = result["content"].splitlines()
            self._display.vvv(
                f"slurp64: split content into {len(result['content_lines'])} " "lines"
            )

        result["changed"] = False

        self._display.vvv("slurp64: finished run(), returning result")
        self._remove_tmp_path(self._connection._shell.tmpdir)

        return result
