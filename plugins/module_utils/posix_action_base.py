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
from datetime import timedelta, timezone
from typing import Any, Dict, List, Optional, Union

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

    def _format_command(self, cmd: Union[str, List[str]]) -> str:
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

    def _normalize_newlines(self, text: str) -> str:
        """
        Normalize Windows-style line endings to Unix-style.

        Converts CRLF (\\r\\n) to LF (\\n) for consistent parsing
        across platforms. This matches the behavior of the builtin
        command module.

        :param str text: Text with potential CRLF line endings
        :returns str: Text with normalized LF line endings
        """
        return text.replace("\r\n", "\n")

    def _is_interpreter_missing(self, result: Dict[str, Any]) -> bool:
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
            self.force_raw = True
            self._display.vv("Python not found, proceeding with raw commands")
            return True

        # Check for shell error indicating Python not found
        # Examples: "/usr/bin/python3: not found", "python: not found"
        python_patterns = [
            "python: not found",
            "python2: not found",
            "python3: not found",
            "/python: not found",  # Catches /usr/bin/python: not found
            "/python2: not found",  # Catches /usr/bin/python2: not found
            "/python3: not found",  # Catches /usr/bin/python3: not found
        ]

        if any(pattern in text_to_check for pattern in python_patterns):
            self.force_raw = True
            self._display.vv(
                "Python interpreter not found (shell error), "
                "proceeding with raw commands"
            )
            return True

        return False

    def _def_inventory_hostname(
        self, task_vars: Optional[Dict[str, Any]] = None
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

    def _get_target_timezone(
        self, task_vars: Optional[Dict[str, Any]] = None
    ) -> timezone:
        """Get target system's timezone as a timezone object.

        Checks for timezone offset in this order:
        1. o0_os facts (o0_os.time.zone.offset)
        2. Standard ansible_facts (ansible_date_time.tz_offset)
        3. Runs 'date +%z' command as fallback

        Falls back to UTC if detection fails.

        :param task_vars: Available Ansible variables
        :returns: timezone object representing target's local timezone
        """
        task_vars = task_vars or {}
        offset_str = None

        # Try o0_os facts first
        o0_os = task_vars.get("o0_os", {})
        if isinstance(o0_os, dict):
            time_facts = o0_os.get("time", {})
            if isinstance(time_facts, dict):
                zone = time_facts.get("zone", {})
                if isinstance(zone, dict):
                    offset_str = zone.get("offset")

        # Try standard ansible_facts if not found
        if not offset_str:
            ansible_facts = task_vars.get("ansible_facts", {})
            if isinstance(ansible_facts, dict):
                date_time = ansible_facts.get("ansible_date_time", {})
                if isinstance(date_time, dict):
                    offset_str = date_time.get("tz_offset")

        # If we found offset in facts, parse and return it
        if offset_str and isinstance(offset_str, str):
            offset_str = offset_str.strip()
            if offset_str:
                try:
                    return self._parse_timezone_offset(offset_str)
                except ValueError:
                    # Invalid offset in facts, fall through to command
                    pass

        # Fallback: run date command
        offset_cmd = self._cmd(
            ["date", "+%z"], task_vars=task_vars, check_mode=False
        )
        if offset_cmd.get("rc") != 0:
            self._display.vvv(
                f"[{self.inventory_hostname}] Failed to get timezone offset, "
                f"assuming UTC"
            )
            return timezone.utc

        offset_str = (offset_cmd.get("stdout") or "").strip()
        if not offset_str:
            return timezone.utc

        try:
            return self._parse_timezone_offset(offset_str)
        except ValueError as e:
            self._display.vvv(
                f"[{self.inventory_hostname}] Failed to parse timezone offset "
                f"'{offset_str}': {e}, assuming UTC"
            )
            return timezone.utc

    def _parse_timezone_offset(self, offset: str) -> timezone:
        """Parse timezone offset string like '-0400' or '+0530'.

        :param offset: Timezone offset string from 'date +%z'
        :returns: timezone object with the specified offset
        :raises ValueError: If offset format is invalid
        """
        if len(offset) != 5 or offset[0] not in ("+", "-"):
            raise ValueError(f"Invalid offset format: {offset}")

        try:
            sign = 1 if offset[0] == "+" else -1
            hours = int(offset[1:3])
            minutes = int(offset[3:5])
        except ValueError:
            raise ValueError(f"Invalid offset format: {offset}")

        offset_delta = timedelta(hours=sign * hours, minutes=sign * minutes)
        return timezone(offset_delta)

    def _run_action(
        self,
        plugin_name: str,
        plugin_args: Dict[str, Any],
        task_vars: Optional[Dict[str, Any]] = None,
        check_mode: Optional[bool] = None,
    ) -> Dict[str, Any]:
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

        if getattr(self, "force_raw", False):
            task.args["_force_raw"] = True

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

        if result.get("raw"):
            self.force_raw = True

        return result

    def _cmd(
        self,
        cmd: Union[str, List[str]],
        stdin: Optional[str] = None,
        chdir: Optional[str] = None,
        strip: bool = True,
        task_vars: Optional[Dict[str, Any]] = None,
        check_mode: Optional[bool] = None,
    ) -> Dict[str, Any]:
        """
        Run the fallback-compatible 'command' action plugin with
        arguments.

        :param Union[str, List[str]] cmd: Command to execute. Can be a
            shell string or a list of arguments
        :param Optional[str] stdin: Optional standard input to pass to
            the command
        :param bool strip: Strip trailing whitespace from output
        :param Optional[dict] task_vars: Dictionary of task variables
            from the calling task
        :param Optional[bool] check_mode: Optional override for Ansible
            check mode
        :returns dict: The result dictionary from the command plugin
        """
        task_vars = task_vars or {}

        args = {
            "stdin": stdin,
            "chdir": chdir,
            "strip_empty_ends": strip,
        }

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
            List[Union[str, List[str]]], Dict[str, Union[str, List[str]]]
        ],
        chdir: Optional[str] = None,
        parallel: bool = True,
        fail_fast: bool = False,
        task_vars: Optional[Dict[str, Any]] = None,
        check_mode: Optional[bool] = None,
    ) -> Union[List[Dict[str, Any]], Dict[str, Dict[str, Any]]]:
        """
        Run multiple commands in a single SSH round trip using the run
        action plugin.

        Dramatically reduces latency by batching commands into a single
        remote execution instead of multiple individual SSH round trips.
        Commands execute in parallel by default for maximum efficiency.

        :param Union[List[Union[str, List[str]]], Dict[str, Union[str,
            List[str]]]] commands: Commands to execute. Can be either:
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
        :returns Union[List[Dict[str, Any]], Dict[str, Dict[str, Any]]]:
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

    def _sanitize_args(self, args: Dict[str, Any]) -> Dict[str, Any]:
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
        self, cmd: str, task_vars: Optional[Dict[str, Any]] = None
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
