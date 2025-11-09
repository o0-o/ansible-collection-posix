# vim: ts=4:sw=4:sts=4:et:ft=python
# -*- mode: python; tab-width: 4; indent-tabs-mode: nil; -*-
#
# GNU General Public License v3.0+
# SPDX-License-Identifier: GPL-3.0-or-later
# (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
#
# Copyright (c) 2025 oØ.o (@o0-o)
#
# Adapted from:
#   - The command module in Ansible core (GPL-3.0-or-later)
#     https://github.com/ansible/ansible/blob/fcffd707c6f8d959d7dc7c6e7a91fa2f59fd0308/lib/ansible/modules/command.py
#
# This file is part of the o0_o.posix Ansible Collection.

from __future__ import annotations

import datetime
import re
from typing import Any, Dict, Optional

from ansible import __version__ as ansible_version
from ansible.errors import AnsibleActionFail
from ansible.plugins.action import ActionBase
from ansible.module_utils.common.text.converters import to_text
from ansible_collections.o0_o.posix.plugins.module_utils import PosixActionBase

try:
    from packaging.version import parse as parse_version
except ImportError as e:
    PACKAGING_IMPORT_ERROR = e
else:
    PACKAGING_IMPORT_ERROR = None


class ActionModule(PosixActionBase, ActionBase):
    """
    Execute a command on the remote host with raw fallback support.

    This action plugin provides robust command execution that
    automatically falls back to raw shell execution when Python is not
    available on the remote host. It supports all standard command
    module features including shell execution, directory changes,
    conditional execution based on file existence, and argument
    validation.

    The plugin first attempts to use the standard Ansible command
    module, and if that fails due to missing Python interpreter,
    it seamlessly falls back to low-level shell execution.

    .. note::
       This plugin requires the 'packaging' Python module for version
       comparison functionality.
    """

    TRANSFERS_FILES = False
    _requires_connection = True
    _supports_check_mode = True
    _supports_async = False

    def _raw_cmd(self) -> None:
        """
        Execute a command using low-level shell methods.

        :raises AnsibleActionFail: When command execution fails or
            arguments are invalid
        """
        if self.expand_vars is not None and self.expand_vars != self.shell:
            raise AnsibleActionFail(
                "Raw fallback requires expand_argument_vars and _uses_shell "
                "to be the same. Shell-based execution expands variables "
                "remotely. If expand_argument_vars is true but _uses_shell is "
                "false, the fallback cannot expand variables."
            )

        # Warn if executable is set without shell=True
        if not self.shell and self.executable:
            self._display.warning(
                f"[{self.inventory_hostname}] As of Ansible 2.4, the "
                "parameter 'executable' is no longer supported with the "
                f"'command' module. Not using '{self.executable}'."
            )
            self.executable = None

        # If chdir is specified, validate the target directory
        # _low_level_command has no specific chdir exception
        if self.chdir:
            quoted_chdir = self._quote(self.chdir)
            cd_result = self._low_level_execute_command(
                f"cd {quoted_chdir}", executable=self.executable
            )
            if cd_result["rc"] != 0:
                raise AnsibleActionFail(
                    "Unable to change directory before execution: "
                    f"{self.chdir}"
                )

        # Use creates/removes logic for check_mode idempotence
        shoulda = "Would" if self._task.check_mode else "Did"

        if self.creates:
            quoted_creates = self._quote(self.creates)
            created = self._low_level_execute_command(
                f"test -e {quoted_creates}"
            )
            if created["rc"] == 0:
                self.result["msg"] = (
                    f"{shoulda} not run command since '{self.creates}' exists"
                )
                self.result["stdout"] = f"skipped, since {self.creates} exists"
                self.result["stdout_lines"] = [self.result["stdout"]]
                self.result["stderr_lines"] = []
                self.result["rc"] = 0
                return

        if self.removes:
            quoted_removes = self._quote(self.removes)
            removed = self._low_level_execute_command(
                f"test -e {quoted_removes}"
            )
            if removed["rc"] != 0:
                self.result["msg"] = (
                    f"{shoulda} not run command since '{self.removes}' "
                    "does not exist"
                )
                self.result["stdout"] = (
                    f"skipped, since {self.removes} does not exist"
                )
                self.result["stdout_lines"] = [self.result["stdout"]]
                self.result["stderr_lines"] = []
                self.result["rc"] = 0
                return

        self.result["changed"] = True

        # Actually run the command unless in check_mode
        if not self._task.check_mode:
            self.result["start"] = datetime.datetime.now()

            # Determine the final command to execute
            if self.shell:
                self.command = self._format_command(
                    ["/bin/sh", "-c", self.command]
                )
            # Execute the command
            exec_result = self._low_level_execute_command(
                self.command,
                in_data=self.stdin,
                executable=self.executable,
                chdir=self.chdir,
            )
            self.result["end"] = datetime.datetime.now()
            self.result.update(exec_result)
        else:
            self.result["rc"] = 0
            self.result["msg"] = (
                "Command would have run if not in check mode"
            )
            if self.creates is None and self.removes is None:
                self.result["skipped"] = True
                self.result["changed"] = False

        # Convert timestamps and delta to text
        if self.result["start"] is not None and self.result["end"] is not None:
            self.result["delta"] = to_text(
                self.result["end"] - self.result["start"]
            )
            self.result["end"] = to_text(self.result["end"])
            self.result["start"] = to_text(self.result["start"])

        # Strip trailing newlines from output if requested and define
        # module stdout/err and stdout/err lines lists.
        if self.result.get("stdout"):
            # Normalize CRLF to LF for consistent parsing
            self.result["stdout"] = self._normalize_newlines(
                to_text(self.result["stdout"])
            )
            if self.strip:
                self.result["stdout"] = self.result["stdout"].rstrip("\r\n")
            self.result["module_stdout"] = self.result["stdout"]
            self.result["stdout_lines"] = self.result["stdout"].splitlines()

        if self.result.get("stderr"):
            # Normalize CRLF to LF for consistent parsing
            stderr_text = self._normalize_newlines(to_text(self.result["stderr"]))
            # Remove SSH "Shared connection to ... closed." message
            self.result["stderr"] = re.sub(
                r"^Shared connection to .* closed\.\r?\n?",
                "",
                stderr_text,
                flags=re.MULTILINE,
            )
            if self.strip:
                self.result["stderr"] = self.result["stderr"].rstrip("\r\n")
            self.result["module_stderr"] = self.result["stderr"]
            self.result["stderr_lines"] = self.result["stderr"].splitlines()

        if self.result["rc"] != 0:
            self.result["msg"] = "non-zero return code"

        return

    def _def_args(self) -> Dict[str, Any]:
        """
        Parse and validate module arguments.

        :returns dict: The validated argument dictionary
        :raises ImportError: When the packaging module is not available
        """
        if PACKAGING_IMPORT_ERROR:
            raise PACKAGING_IMPORT_ERROR

        argument_spec = {
            "_uses_shell": {"type": "bool", "default": False},
            "cmd": {"type": "str"},
            "argv": {"type": "list", "elements": "str"},
            "chdir": {"type": "path"},
            "executable": {"type": "str"},
            "expand_argument_vars": {"type": "bool"},
            "creates": {"type": "path"},
            "removes": {"type": "path"},
            "stdin": {"required": False},
            "stdin_add_newline": {"type": "bool", "default": True},
            "strip_empty_ends": {"type": "bool", "default": True},
            "_force_raw": {"type": "bool", "default": False},
        }
        mutually_exclusive = [["cmd", "argv"]]
        required_one_of = [["cmd", "argv"]]

        validation_result, new_module_args = self.validate_argument_spec(
            argument_spec=argument_spec,
            mutually_exclusive=mutually_exclusive,
            required_one_of=required_one_of,
        )
        self.shell = new_module_args["_uses_shell"]
        self.chdir = new_module_args["chdir"]
        self.executable = new_module_args["executable"]
        self.creates = new_module_args["creates"]
        self.removes = new_module_args["removes"]
        self.strip = new_module_args["strip_empty_ends"]
        self.force_raw = new_module_args.pop("_force_raw")

        # Args
        cmd = new_module_args.pop("cmd")
        if cmd is not None:
            # Avoid errors when using builtin command module
            new_module_args["_raw_params"] = cmd
        argv = new_module_args["argv"]
        if argv is None:
            # Avoid errors when using builtin command module
            new_module_args.pop("argv")
        self.command = cmd or argv
        if not self.shell:
            self.command = self._format_command(self.command)

        # Stdin
        self.stdin = new_module_args["stdin"]
        self.stdin_add_newline = new_module_args["stdin_add_newline"]
        if self.stdin and self.stdin_add_newline:
            if not self.stdin.endswith("\n"):
                self.stdin = self.stdin + "\n"
        if isinstance(self.stdin, str):
            self.stdin = self.stdin.encode("utf-8")

        # Expand vars
        self.expand_vars = new_module_args["expand_argument_vars"]
        if self.expand_vars is None:
            # Avoid errors when using builtin command module
            new_module_args.pop("expand_argument_vars")
        elif parse_version(ansible_version) < parse_version("2.16"):
            raise AnsibleActionFail(
                "expand_argument_vars is not supported on Ansible "
                "versions before 2.16"
            )

        return new_module_args

    def run(
        self,
        tmp: Optional[str] = None,
        task_vars: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Execute the command action with raw fallback capability.

        :param Optional[str] tmp: Temporary directory path (unused)
        :param Optional[Dict[str, Any]] task_vars: Task variables
        :returns Dict[str, Any]: Ansible result dictionary
        :raises AnsibleActionFail: When packaging module is missing or
            command execution fails
        """
        task_vars = task_vars or {}
        self._def_inventory_hostname(task_vars)

        try:
            new_module_args = self._def_args()
        except ImportError as e:
            raise AnsibleActionFail(
                "The 'packaging' Python module is required to run this "
                f"plugin. Import failed: {e}"
            )

        self.result = super(ActionModule, self).run(tmp, task_vars=task_vars)
        self.result.update(
            {
                "cmd": self.command,
                "changed": False,
                "stdout": "",
                "stderr": "",
                "rc": None,
                "cmd": None,
                "start": None,
                "end": None,
                "delta": None,
                "msg": "",
                "invocation": self._task.args.copy(),
            }
        )

        del tmp

        if not self.force_raw:
            builtin_module_args = new_module_args.copy()

            builtin_module_result = self._execute_module(
                module_name="ansible.builtin.command",
                module_args=builtin_module_args,
                task_vars=task_vars,
            )
            builtin_module_result.pop("invocation")

            if self._is_interpreter_missing(builtin_module_result):
                self._display.warning(
                    f"[{self.inventory_hostname}] Ansible command module "
                    "failed; falling back to raw command."
                )
                self.force_raw = True
            else:
                self.result.update(builtin_module_result)
                self.result["raw"] = False

        if self.force_raw:  # Must check again instead of else
            self.result["raw"] = True
            self._raw_cmd()

        self._remove_tmp_path(self._connection._shell.tmpdir)

        return self.result
