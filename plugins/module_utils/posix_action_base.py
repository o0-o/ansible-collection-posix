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

import difflib
import hashlib
import shlex
import stat
from datetime import datetime, timedelta, timezone
from os import path
from typing import Any, Dict, List, Optional, Union, Tuple

from ansible.module_utils.common.text.converters import to_text


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
        elements for shell execution.

        :param cmd: Command as string or list of arguments
        :returns str: Shell-safe command string
        """
        if isinstance(cmd, str):
            return cmd

        # Use shlex.join() if available (Python 3.8+)
        try:
            return shlex.join(cmd)
        except AttributeError:
            # Python < 3.8 fallback
            return " ".join(shlex.quote(str(arg)) for arg in cmd)

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

    def _get_inventory_hostname(
        self, task_vars: Optional[Dict[str, Any]] = None
    ) -> str:
        """Return the inventory hostname for log/warning messages.

        Prefers the value from ``task_vars`` when provided, then falls
        back to the task's vars mapping. Defaults to ``localhost`` when
        no value can be determined (e.g., local actions).

        :param task_vars: Optional task vars mapping
        :returns: Hostname string suitable for log prefixes
        """
        if isinstance(task_vars, dict):
            host = task_vars.get("inventory_hostname")
            if host:
                return str(host)

        try:
            mapping = getattr(self._task, "vars", None)
            if isinstance(mapping, dict):
                host = mapping.get("inventory_hostname")
                if host:
                    return str(host)
        except Exception:
            pass

        return "localhost"

    def _get_target_timezone(
        self, task_vars: Optional[Dict[str, Any]] = None
    ) -> timezone:
        """Get target system's timezone as a timezone object.

        Uses 'date +%z' to get the UTC offset (e.g., '-0400').
        Falls back to UTC if detection fails.

        :param task_vars: Available Ansible variables
        :returns: timezone object representing target's local timezone
        """
        offset_cmd = self._cmd(
            ["date", "+%z"], task_vars=task_vars, check_mode=False
        )
        if offset_cmd.get("rc") != 0:
            host = self._get_inventory_hostname(task_vars)
            self._display.vvv(
                f"[{host}] Failed to get timezone offset, assuming UTC"
            )
            return timezone.utc

        offset_str = (offset_cmd.get("stdout") or "").strip()
        if not offset_str:
            return timezone.utc

        try:
            return self._parse_timezone_offset(offset_str)
        except ValueError as e:
            host = self._get_inventory_hostname(task_vars)
            self._display.vvv(
                f"[{host}] Failed to parse timezone offset "
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
        }

        if isinstance(cmd, list):
            args["argv"] = cmd
        elif isinstance(cmd, str):
            args["cmd"] = cmd
            args["_uses_shell"] = True
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
        commands: List[Union[str, List[str]]],
        chdir: Optional[str] = None,
        fail_fast: bool = False,
        task_vars: Optional[Dict[str, Any]] = None,
        check_mode: Optional[bool] = None,
    ) -> Dict[str, Any]:
        """
        Run multiple commands in a single SSH round trip using the run
        action plugin.

        Dramatically reduces latency by batching commands into a single
        remote execution instead of multiple individual SSH round trips.

        :param List[Union[str, List[str]]] commands: List of commands to
            execute. Each can be a shell string or list of arguments
        :param Optional[str] chdir: Change to this directory before
            executing commands
            not exist
        :param bool fail_fast: Stop on first command failure (default
            False)
        :param Optional[dict] task_vars: Dictionary of task variables
        :param Optional[bool] check_mode: Optional override for Ansible
            check mode
        :returns dict: Result dictionary with 'commands' list containing
            individual command outputs
        """
        task_vars = task_vars or {}

        args = {
            "commands": commands,
            "fail_fast": fail_fast,
        }

        if chdir:
            args["chdir"] = chdir
        if creates:
            args["creates"] = creates
        if removes:
            args["removes"] = removes

        return self._run_action(
            "o0_o.posix.run",
            args,
            task_vars=task_vars,
            check_mode=check_mode,
        )

    def _read(
        self,
        path: Optional[str] = None,
        paths: Optional[List[str]] = None,
        include: Optional[List[str]] = None,
        encoding: Optional[str] = None,
        parents: Optional[bool] = None,
        find_hardlinks: bool = False,
        find_symlinks: bool = False,
        task_vars: Optional[Dict[str, Any]] = None,
        check_mode: Optional[bool] = None,
    ) -> Dict[str, Any]:
        """
        Run the read action plugin to gather file metadata and content.

        Inspects file metadata and optionally content on POSIX hosts using
        portable commands. When path does not exist, returns null instead
        of raising an error.

        :param Optional[str] path: Absolute path to the file to inspect
        :param Optional[List[str]] paths: List of paths to inspect
        :param Optional[List[str]] include: List of field names to include
            (metadata, content, type, name, parent, mode, owner, group,
            writable, links, modified, created, acl, xattrs, flags, selinux)
        :param Optional[str] encoding: Override detected encoding for content
        :param Optional[bool] parents: Include parent directories (False,
            True, or integer count)
        :param bool find_hardlinks: Enumerate all hard link paths
        :param bool find_symlinks: Enumerate all symbolic links
        :param Optional[dict] task_vars: Dictionary of task variables
        :param Optional[bool] check_mode: Optional override for Ansible
            check mode
        :returns dict: Result dictionary with 'paths' containing file data
        """
        task_vars = task_vars or {}

        args = {
            "find_hardlinks": find_hardlinks,
            "find_symlinks": find_symlinks,
        }

        if path:
            args["path"] = path
        if paths:
            args["paths"] = paths
        if include:
            args["include"] = include
        if encoding:
            args["encoding"] = encoding
        if parents is not None:
            args["parents"] = parents

        return self._run_action(
            "o0_o.posix.read",
            args,
            task_vars=task_vars,
            check_mode=check_mode,
        )

    def _stat(
        self,
        path: str,
        follow: bool = False,
        get_checksum: bool = True,
        get_mime: bool = True,
        get_attributes: bool = True,
        checksum_algorithm: str = "sha1",
        task_vars: Optional[Dict[str, Any]] = None,
        check_mode: Optional[bool] = None,
    ) -> Dict[str, Any]:
        """
        Run the stat action plugin to gather file status information.

        Retrieves file status information similar to the stat command,
        including permissions, ownership, timestamps, checksums, and more.

        :param str path: Path to the file to stat
        :param bool follow: Follow symbolic links (default False)
        :param bool get_checksum: Calculate file checksum (default True)
        :param bool get_mime: Get MIME type (default True)
        :param bool get_attributes: Get file attributes (default True)
        :param str checksum_algorithm: Algorithm for checksum (default sha1)
        :param Optional[dict] task_vars: Dictionary of task variables
        :param Optional[bool] check_mode: Optional override for Ansible
            check mode
        :returns dict: Result dictionary with stat information

        .. note::
           The _force_raw flag is automatically added by _run_action if
           self.force_raw is True, so no need to pass it explicitly.
        """
        task_vars = task_vars or {}

        args = {
            "path": path,
            "follow": follow,
            "get_checksum": get_checksum,
            "get_mime": get_mime,
            "get_attributes": get_attributes,
            "checksum_algorithm": checksum_algorithm,
        }

        return self._run_action(
            "o0_o.posix.stat",
            args,
            task_vars=task_vars,
            check_mode=check_mode,
        )

    def _cat(
        self, src: str, task_vars: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Fallback method to read the contents of a file using 'cat'.

        :param str src: Path to the file on the remote host
        :param Optional[dict] task_vars: Dictionary of task variables
            from the calling task
        :returns dict: Dictionary with read result or error
        """
        cmd_result = self._cmd(
            ["cat", src], task_vars=task_vars, check_mode=False
        )
        result = {"changed": False, "raw": cmd_result.get("raw", False)}
        result["source"] = src

        stdout = cmd_result.pop("stdout", None)
        stderr = cmd_result.pop("stderr", None)

        if cmd_result.get("rc") != 0:
            result["failed"] = True
            result["msg"] = stderr.strip() or stdout.strip()
        else:
            result["content"] = stdout.replace("\r", "")

        return result

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
        cmd_result = self._cmd(["sh", "-c", shell_cmd], task_vars=task_vars)
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
