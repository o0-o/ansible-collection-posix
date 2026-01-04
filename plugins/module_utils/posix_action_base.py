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

"""
Shared helpers for action plugin compatibility and fallback execution.

This module provides utilities to detect interpreter presence and to
manually invoke other action plugins (e.g. command, slurp64) using
FQCNs.
Used by custom action plugins to gracefully degrade to raw execution
when Python is not available on the remote host.
"""

from __future__ import annotations

import shlex
from typing import Any, Optional, Union

from ansible.module_utils.common.text.converters import to_native


class PosixActionBase:
    """
    Mixin class for POSIX-compatible Ansible action plugins with raw
    fallback support.

    This mixin provides shared helpers for action plugins that must
    operate on remote hosts without a working Python interpreter.

    It implements fallback-compatible versions of common file and shell
    operations, including command execution, file slurping, directory
    creation, and secure file writing with backup, validation, and
    SELinux support. It also enables inter-plugin delegation using fully
    qualified collection names (FQCNs).

    This mixin is intended for use in collections targeting POSIX
    systems. All operations rely exclusively on POSIX-standard tools
    such as `cat`, `mv`, `cp`, `mkdir`, `chown`, `chmod`, and `printf`.
    Non-portable utilities like `install` are deliberately avoided.

    Usage:
        from ansible.plugins.action import ActionBase
        from ansible_collections.o0_o.posix.plugins.module_utils \
            import PosixActionBase

        class ActionModule(PosixActionBase, ActionBase):
            def run(self, tmp=None, task_vars=None):
                ...
    """

    def _format_command(self, cmd: Union[str, list[str]]) -> str:
        """
        Convert a command to a shell-safe string.

        Handles both string and list inputs, properly quoting list
        elements for shell execution. List elements are automatically
        converted to native strings to handle non-string types like
        integers or Path objects.

        :param cmd: Command as string or list of arguments
        :returns str: Shell-safe command string
        """
        if isinstance(cmd, str):
            # Validate syntax and normalize quoting by tokenizing
            # and re-joining
            cmd = shlex.split(cmd)
        else:
            # Convert all list elements to native strings
            cmd = [
                to_native(
                    arg, errors="surrogate_or_strict", nonstring="simplerepr"
                )
                for arg in cmd
            ]
        try:
            # Use shlex.join() if available (Python 3.8+)
            return shlex.join(cmd)
        except AttributeError:
            # Python < 3.8 fallback
            return " ".join(shlex.quote(str(arg)) for arg in cmd)
        return cmd

    def _flags_to_octal_mode(self, flags: str) -> str:
        """
        Convert ls permission flags to octal mode string.

        Parses the 10-character permission string from ls output
        (e.g., "-rwxr-xr-x") and converts it to a 4-digit octal
        mode string (e.g., "0755").

        :param str flags: Permission flags from ls (10 characters)
        :returns str: Octal mode as 4-digit string (e.g., "0755")
        """
        if not flags or len(flags) < 10:
            return "0000"

        perms = flags[1:]  # Skip first char (file type)
        octal = 0

        # Owner permissions
        if perms[0] == "r":
            octal += 0o400
        if perms[1] == "w":
            octal += 0o200
        if perms[2] in ["x", "s", "S"]:
            octal += 0o100
        if perms[2] in ["s", "S"]:
            octal += 0o4000  # setuid

        # Group permissions
        if perms[3] == "r":
            octal += 0o040
        if perms[4] == "w":
            octal += 0o020
        if perms[5] in ["x", "s", "S"]:
            octal += 0o010
        if perms[5] in ["s", "S"]:
            octal += 0o2000  # setgid

        # Other permissions
        if perms[6] == "r":
            octal += 0o004
        if perms[7] == "w":
            octal += 0o002
        if perms[8] in ["x", "t", "T"]:
            octal += 0o001
        if perms[8] in ["t", "T"]:
            octal += 0o1000  # sticky bit

        return f"{octal:04o}"

    def _is_interpreter_missing(self, result: dict[str, Any]) -> bool:
        """
        Check if failure was likely caused by a missing Python
        interpreter.

        :param result: A result dict from _execute_module or fallback
            command
        :returns bool: True if failure likely due to missing Python,
            else False
        """
        if not isinstance(result, dict):
            return False

        if result.get("rc") != 127:
            return False

        msg = result.get("msg", "")
        stderr = result.get("stderr", "")
        module_stderr = result.get("module_stderr", "")
        module_stdout = result.get("module_stdout", "")

        # Check all text fields for interpreter errors
        text_to_check = " ".join(
            [
                str(msg) if isinstance(msg, str) else "",
                str(stderr) if isinstance(stderr, str) else "",
                str(module_stderr) if isinstance(module_stderr, str) else "",
                str(module_stdout) if isinstance(module_stdout, str) else "",
            ]
        ).lower()

        # Ansible's standard error message
        canary_str = (
            "The module failed to execute correctly, you probably need to set "
            "the interpreter"
        )

        # Check for the standard canary or signs of missing Python
        if canary_str.lower() in text_to_check:
            self._display.vv("Python interpreter not found")
            return True

        # Check for shell error indicating Python not found
        # Examples: "/usr/bin/python3: not found", "python: not found"
        python_patterns = [
            "python: not found",
            "python2: not found",
            "python3: not found",
        ]

        if any(pattern in text_to_check for pattern in python_patterns):
            self._display.vv("Python interpreter not found (shell error)")
            return True

        return False

    def _def_inventory_hostname(
        self, task_vars: Optional[dict[str, Any]] = None
    ) -> str:
        """Get/define the inventory hostname for log/warning messages.

        Prefers the value from ``task_vars`` when provided, then falls
        back to the task's vars mapping. Defaults to ``localhost`` when
        no value can be determined (e.g., local actions).

        Sets self.inventory_hostname and returns the value.

        :param task_vars: Optional task vars mapping
        :returns str: The inventory hostname or 'localhost' as fallback
        """
        if isinstance(task_vars, dict):
            host = task_vars.get("inventory_hostname")
            if host:
                self.inventory_hostname = str(host)
                return self.inventory_hostname

        try:
            mapping = getattr(self._task, "vars", None)
            if isinstance(mapping, dict):
                host = mapping.get("inventory_hostname")
                if host:
                    self.inventory_hostname = str(host)
                    return self.inventory_hostname
        except Exception:
            pass

        self.inventory_hostname = "localhost"
        return self.inventory_hostname

    def _run_action(
        self,
        plugin_name: str,
        plugin_args: dict[str, Any],
        task_vars: Optional[dict[str, Any]] = None,
        check_mode: Optional[bool] = None,
    ) -> dict[str, Any]:
        """
        Execute another action plugin using the provided arguments.

        :param str plugin_name: Fully qualified name of the plugin to
            run (e.g. 'ansible.builtin.command')
        :param dict plugin_args: Dictionary of arguments to pass to the
            plugin
        :param Optional[dict] task_vars: Dictionary of task variables
            from the calling task
        :param Optional[bool] check_mode: Override check mode setting
        :returns dict: The result dictionary returned by the plugin's
            run method
        """
        current_fqcn = self._task.action.lower().strip()
        requested_fqcn = plugin_name.lower().strip()

        if requested_fqcn == current_fqcn:
            raise RecursionError(
                f"CompatAction attempted to call '{plugin_name}' from within "
                "itself. This would result in infinite recursion."
            )

        task = self._task.copy()
        task.args.clear()
        task.args.update(plugin_args)

        if getattr(self, "raw", False):
            task.args["raw"] = True

        plugin = self._shared_loader_obj.action_loader.get(
            plugin_name,
            task=task,
            connection=self._connection,
            play_context=self._play_context,
            loader=self._loader,
            templar=self._templar,
            shared_loader_obj=self._shared_loader_obj,
        )

        if plugin is None:
            return self._execute_module(
                module_name=plugin_name,
                module_args=plugin_args,
                task_vars=task_vars,
            )

        if check_mode is not None:
            plugin._task.check_mode = check_mode

        result = plugin.run(task_vars=task_vars)

        # Update raw mode based on delegated plugin's result
        if "raw" in result:
            if getattr(self, "raw", None) == "auto":
                self.raw = result["raw"]
            elif result["raw"]:
                self.raw = True

        return result

    def _cmd(
        self,
        cmd: Union[str, list[str]],
        stdin: Optional[str] = None,
        chdir: Optional[str] = None,
        strip: bool = True,
        task_vars: Optional[dict[str, Any]] = None,
        check_mode: Optional[bool] = None,
        raw: Optional[Union[bool, str]] = None,
    ) -> dict[str, Any]:
        """
        Run the fallback-compatible 'command' action plugin with
        arguments.

        :param Union[str, list[str]] cmd: Command to execute. Can be a
            shell string or a list of arguments
        :param Optional[str] stdin: Optional standard input to pass to
            the command
        :param bool strip: Strip trailing whitespace from output
        :param Optional[dict] task_vars: Dictionary of task variables
            from the calling task
        :param Optional[bool] check_mode: Optional override for Ansible
            check mode
        :param Optional[Union[bool, str]] raw: Force raw execution
            (True/False) or auto-detect ("auto")
        :returns dict: The result dictionary from the command plugin
        """
        task_vars = task_vars or {}

        args = {
            "stdin": stdin,
            "chdir": chdir,
            "strip_empty_ends": strip,
        }

        # Pass raw if explicitly set
        if raw is not None:
            args["raw"] = raw

        if isinstance(cmd, str):
            args["cmd"] = cmd
            args["_uses_shell"] = True
        elif isinstance(cmd, list):
            args["argv"] = cmd
        else:
            raise TypeError(
                f"Expected cmd to be str or list, got {type(cmd).__name__}"
            )

        return self._run_action(
            "o0_o.posix.command",
            args,
            task_vars=task_vars,
            check_mode=check_mode,
        )

    def _run(
        self,
        commands: Union[
            list[Union[str, list[str]]], dict[str, Union[str, list[str]]]
        ],
        chdir: Optional[str] = None,
        parallel: bool = True,
        fail_fast: bool = False,
        task_vars: Optional[dict[str, Any]] = None,
        check_mode: Optional[bool] = None,
    ) -> Union[list[dict[str, Any]], dict[str, dict[str, Any]]]:
        """
        Run multiple commands in a single SSH round trip using the run
        action plugin.

        Dramatically reduces latency by batching commands into a single
        remote execution instead of multiple individual SSH round trips.
        Commands execute in parallel by default for maximum efficiency.

        :param Union[list[Union[str, list[str]]], dict[str, Union[str,
            list[str]]]] commands: Commands to execute. Can be either:
            - List of commands (returns list of results)
            - Dict mapping keys to commands (returns dict mapping same
              keys to results)
        :param Optional[str] chdir: Change to this directory before
            executing commands
        :param bool parallel: Execute commands in parallel using
            background jobs (default True)
        :param bool fail_fast: Stop on first command failure (default
            False)
        :param Optional[dict] task_vars: Dictionary of task variables
        :param Optional[bool] check_mode: Optional override for Ansible
            check mode
        :returns Union[list[dict[str, Any]], dict[str, dict[str, Any]]]:
            If commands is a list, returns list of command results.
            If commands is a dict, returns dict mapping keys to results.
        """
        task_vars = task_vars or {}

        args = {
            "commands": commands,
            "parallel": parallel,
            "fail_fast": fail_fast,
        }

        if chdir:
            args["chdir"] = chdir

        return self._run_action(
            "o0_o.posix.run",
            args,
            task_vars=task_vars,
            check_mode=check_mode,
        )

    def _sanitize_args(self, args: dict[str, Any]) -> dict[str, Any]:
        """
        Return a copy of the argument dictionary with all None values
        removed.

        This is useful when passing arguments to Ansible modules that
        enforce mutually exclusive parameters or expect missing values
        to be omitted rather than explicitly set to null/None.

        :param dict args: Dictionary of module arguments to sanitize
        :returns dict: A new dictionary with all None values removed
        """
        return {k: v for k, v in args.items() if v is not None}

    def _quote(self, s: str) -> str:
        """
        Quote a string for safe use in shell commands.

        Uses the remote connection's shell quoting logic if available
        (e.g., for non-POSIX shells), falling back to Python's
        ``shlex.quote()`` for standard POSIX-compatible escaping.

        :param str s: The string to quote
        :returns str: The safely quoted string
        """
        shell = self._connection._shell
        return getattr(shell, "quote", shlex.quote)(s)

    def _which(
        self, cmd: str, task_vars: Optional[dict[str, Any]] = None
    ) -> Optional[str]:
        """
        Locate the full path of a command using POSIX-compliant methods.

        Attempts to resolve the path to an executable by first using the
        POSIX-compliant ``command -v``, and falls back to ``which`` if
        necessary. If the command is a shell builtin or function,
        returns its name.

        :param str cmd: The name of the command to locate
            (e.g., "chcon")
        :param Optional[dict] task_vars: Ansible task variables passed
            to the ``_cmd`` method
        :returns Optional[str]: Path to the command or the name if it's
            a shell builtin
        """
        quoted = shlex.quote(cmd)
        shell_cmd = f"unalias -a 2>/dev/null; command -v {quoted}"
        cmd_result = self._cmd(shell_cmd, task_vars=task_vars)
        stdout = cmd_result.get("stdout", "").strip()

        if cmd_result["rc"] == 0 and stdout:
            # If stdout is just the command name (no slash), assume
            # builtin
            if "/" not in stdout:
                return cmd
            return stdout
        else:
            self._display.vvv(f"command -v {cmd} failed, trying which")

        # Fallback to 'which' if available
        cmd_result = self._cmd(["which", cmd], task_vars=task_vars)
        stdout = cmd_result.get("stdout", "").strip()
        stdout_lower = stdout.lower()

        if cmd_result["rc"] == 0 and stdout:
            # Detect builtin shell descriptions from common formats
            if (
                "shell built-in command" in stdout_lower
                or "shell builtin" in stdout_lower
            ):
                return cmd
            if stdout and "/" not in stdout:
                return cmd
            return stdout

        self._display.vvv(f"which failed, {cmd} command not found.")

        return None
