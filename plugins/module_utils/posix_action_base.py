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

    def _format_command_list(
        self, commands: List[Union[str, List[str]]]
    ) -> List[str]:
        """
        Convert a list of commands to shell-safe strings.

        :param commands: List of commands (each as string or list)
        :returns List[str]: List of shell-safe command strings
        """
        return [self._format_command(cmd) for cmd in commands]

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

    def _pseudo_stat(
        self, target_path: str, task_vars: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Fallback-compatible file stat using POSIX ``test`` commands.

        This method uses a combination of ``test`` shell commands to
        detect if a remote path exists, what type of object it is (e.g.,
        file, directory, etc.), and whether it is a symlink.

        :param str target_path: The remote path to test
        :param Optional[dict] task_vars: Ansible task_vars from run(),
            passed to _cmd()
        :returns dict: Dictionary with keys 'exists' (bool), 'type'
            (str or None), 'is_symlink' (bool), 'raw' (bool)
        :raises RuntimeError: if type cannot be determined
        """
        exists_test = self._cmd(
            ["test", "-e", target_path], task_vars=task_vars, check_mode=False
        )

        result = {"raw": exists_test.get("raw", False)}

        if exists_test["rc"] != 0:
            result["exists"] = False
            result["type"] = None
            return result

        result["exists"] = True

        symlink_test = self._cmd(
            ["test", "-L", target_path], task_vars=task_vars, check_mode=False
        )

        result["is_symlink"] = symlink_test["rc"] == 0

        type_tests = [
            ("directory", ["-d"]),
            ("file", ["-f"]),
            ("block", ["-b"]),
            ("char", ["-c"]),
            ("pipe", ["-p"]),
            ("socket", ["-S"]),
        ]

        for type_name, flag in type_tests:
            check = self._cmd(
                ["test"] + flag + [target_path],
                task_vars=task_vars,
                check_mode=False,
            )
            if check["rc"] == 0:
                result["type"] = type_name
                return result

        raise RuntimeError(
            f"All POSIX 'test' commands failed on '{target_path}'"
        )

    def _mkdir(
        self,
        target_path: str,
        task_vars: Optional[Dict[str, Any]] = None,
        parents: Optional[bool] = True,
        mode: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Ensure a directory exists on the remote host.

        Creates a directory on the remote host using fallback-compatible
        methods, optionally applying a permission mode.

        :param str target_path: The remote directory path to create
        :param Optional[dict] task_vars: Ansible task_vars from
            ``run()``
        :param bool parents: Whether to create parent directories
            (``mkdir -p``)
        :param Optional[str] mode: Optional permission mode string
            (e.g. "0755")
        :returns dict: Dictionary with ``changed`` boolean key
        :raises RuntimeError: On directory creation error
        """
        self._display.vvv(f"Creating directory: {target_path}")

        # Check if the path exists
        stat = self._pseudo_stat(target_path, task_vars=task_vars)
        if stat["type"] == "directory":
            self._display.vvv(f"Directory already exists: {target_path}")
            return {"rc": 0, "changed": False}
        if stat["exists"]:
            raise NotADirectoryError(
                f"Path '{target_path}' exists but is not a directory "
                f"({stat['type']})"
            )

        # Attempt to create directory
        args = ["mkdir"]
        if parents:
            args.append("-p")
        if mode:
            args.extend(["-m", mode])
        args.append(target_path)

        mkdir_result = self._cmd(args, task_vars=task_vars)
        if mkdir_result["rc"] != 0:
            raise RuntimeError(
                f"Failed to create directory '{target_path}': "
                f"{mkdir_result.get('stderr', '').strip()}"
            )

        return {"rc": mkdir_result["rc"], "changed": True, "raw": stat["raw"]}

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

    def _generate_ansible_backup_path(self, target_path: str) -> str:
        """
        Generate an Ansible-style backup file name based on the path.

        The format is: ``<path>.<md5_digest>.<UTC timestamp>``

        :param str target_path: The full remote file path to back up
        :returns str: Backup file name as a string
        """
        digest = hashlib.md5(target_path.encode("utf-8")).hexdigest()
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        return f"{target_path}.{digest}.{timestamp}"

    def _validate_file(
        self,
        tmpfile: str,
        validate_cmd: str,
        task_vars: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Run a validation command against a temporary file.

        :param str tmpfile: The temporary file to validate
        :param str validate_cmd: The validation command template
        :param Optional[dict] task_vars: Task vars from the calling
            action
        :raises RuntimeError: If validation fails
        """
        self._display.vvv(f"Validating {tmpfile}")
        if not validate_cmd:
            return

        cmd = validate_cmd % self._quote(tmpfile)
        result = self._cmd(cmd, task_vars=task_vars)

        if result["rc"] != 0:
            raise RuntimeError(
                f"Validation failed: {validate_cmd} => "
                f"{result.get('stderr', '')}"
            )

    def _create_backup(
        self, dest: str, task_vars: Optional[Dict[str, Any]] = None
    ) -> Optional[str]:
        """
        Create a backup of the destination file if it exists.

        :param str dest: Destination file to back up
        :param Optional[dict] task_vars: Task vars from the calling
            action
        :returns Optional[str]: Path to the backup file or None if not
            created
        :raises RuntimeError: If backup fails
        """
        result = self._cmd(["test", "-e", dest], task_vars=task_vars)
        if result["rc"] != 0:
            return None

        backup_path = self._generate_ansible_backup_path(dest)
        self._display.vvv(f"Creating backup at {backup_path}")
        result = self._cmd(
            ["cp", "--preserve=all", dest, backup_path], task_vars=task_vars
        )

        if result["rc"] != 0:
            raise RuntimeError(f"Backup failed: {result.get('stderr', '')}")

        return backup_path

    def _handle_selinux_context(
        self,
        dest: str,
        perms: Dict[str, Any],
        task_vars: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Apply SELinux context to the destination file.

        If both ``semanage`` and ``restorecon`` are available, persist
        the context via semanage and apply it with restorecon.
        Otherwise, fall back to ``chcon``.

        :param str dest: Target file path on the remote host
        :param dict perms: Dictionary of SELinux keys (seuser, serole,
            setype, selevel)
        :param Optional[dict] task_vars: Ansible task_vars from the
            calling context
        :raises RuntimeError: If context application fails
        """
        self._display.vvv(f"Handling SELinux for {dest}")
        if not perms:
            return

        selinux_keys = [
            k
            for k in ("selevel", "serole", "setype", "seuser")
            if perms.get(k)
        ]
        if not selinux_keys:
            return

        setype = perms.get("setype")
        seuser = perms.get("seuser")
        serole = perms.get("serole")
        selevel = perms.get("selevel")

        # Try semanage if available and setype is defined
        semanage_path = self._which("semanage", task_vars=task_vars)
        restorecon_path = self._which("restorecon", task_vars=task_vars)

        if semanage_path and restorecon_path and setype:
            fcontext_type = setype
            semanage_cmd = [
                "semanage",
                "fcontext",
                "-a",
                "-t",
                fcontext_type,
                dest,
            ]
            result = self._cmd(semanage_cmd, task_vars=task_vars)
            if result["rc"] != 0:
                raise RuntimeError(
                    "Failed to register SELinux context with semanage: "
                    f"{result.get('stderr', '')}"
                )

            restorecon_cmd = ["restorecon", dest]
            result = self._cmd(restorecon_cmd, task_vars=task_vars)
            if result["rc"] != 0:
                raise RuntimeError(
                    "Failed to apply SELinux context with restorecon: "
                    f"{result.get('stderr', '')}"
                )
            return

        # Fallback to chcon if available
        chcon_cmd = ["chcon"]
        if seuser:
            chcon_cmd += ["-u", seuser]
        if serole:
            chcon_cmd += ["-r", serole]
        if setype:
            chcon_cmd += ["-t", setype]
        if selevel:
            chcon_cmd += ["-l", selevel]
        chcon_cmd.append(dest)

        result = self._cmd(chcon_cmd, task_vars=task_vars)
        if result["rc"] != 0:
            raise RuntimeError(
                "Failed to set SELinux context with chcon: "
                f"{result.get('stderr', '')}"
            )

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

    def _get_perms(
        self,
        target: str,
        selinux: bool = False,
        task_vars: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Retrieve POSIX file permissions using ``ls``.

        Retrieves POSIX file permissions and optionally SELinux context
        for a given file or directory. When ``selinux=True``, the
        SELinux context (if available) is also parsed and returned
        alongside mode, owner, and group. Any trailing ACL/attribute
        indicators (e.g., "+", "@") are stripped from the mode field.

        :param str target: Path to the file or directory to inspect
        :param bool selinux: Whether to include SELinux context
            information
        :param Optional[dict] task_vars: Ansible task variables for
            command execution
        :returns dict: Dictionary containing file permissions with keys:
            - ``mode`` (str): Symbolic file mode (e.g., "-rw-r--r--")
            - ``owner`` (str): File owner
            - ``group`` (str): File group
            - Optional SELinux keys: ``seuser``, ``setype``, ``serole``,
              ``selevel``
        :raises RuntimeError: If the ``ls`` command fails or
            produces unexpected output
        """
        self._display.vvv(f"Getting permissions of {target}")
        ls_args = ["ls"]
        if selinux:
            ls_args.append("-Zd")
        else:
            ls_args.append("-ld")
        ls_args.append(target)

        cmd_result = self._cmd(ls_args, task_vars=task_vars)
        if cmd_result["rc"] != 0:
            raise RuntimeError(
                f"Could not stat {target}: {cmd_result['stderr']}"
            )

        parts = cmd_result["stdout_lines"][0].split()

        if selinux:
            try:
                # Format: context user:role:type:level owner group ...
                context = parts[0]
                mode = parts[1][1:10]  # Trim type and ACL symbols
                owner = parts[2]
                group = parts[3]
                seuser, serole, setype, selevel = context.split(":")
            except Exception:
                raise RuntimeError(
                    "Unexpected SELinux output from ls -Zd: "
                    f"{cmd_result['stdout']}"
                )

            return {
                "mode": mode,
                "owner": owner,
                "group": group,
                "seuser": seuser,
                "serole": serole,
                "setype": setype,
                "selevel": selevel,
            }

        else:
            mode = parts[0][1:10]  # Trim type and ACL symbols
            owner = parts[2]
            group = parts[3]
            return {
                "mode": mode,
                "owner": owner,
                "group": group,
            }

    def _normalize_content(
        self, content: Union[str, List[str]]
    ) -> Tuple[List[str], str]:
        """
        Normalize input content to a list of lines and string.

        Accepts either a string or a list of strings/numbers. Ensures
        the output string ends with a newline character and all list
        elements are converted to strings. Raises an RuntimeError
        on unsupported input types.

        :param Union[str, List[Union[str, int, float]]] content: The
            input to normalize
        :returns Tuple[List[str], str]: Tuple of (lines, content)
        :raises RuntimeError: If input is of invalid type or
            contains non-stringlike items
        """
        if isinstance(content, str):
            lines = content.splitlines()
            normalized = content if content.endswith("\n") else content + "\n"
        elif isinstance(content, list):
            if not all(
                isinstance(line, (str, int, float)) for line in content
            ):
                raise RuntimeError("_write_file() requires strings or numbers")
            lines = [str(line) for line in content]
            normalized = "\n".join(lines) + "\n"
        else:
            raise RuntimeError(
                "_write_file() requires a string or list of strings"
            )
        self._display.vvv(f"Normalized lines: {lines}")
        return lines, normalized

    def _write_temp_file(
        self,
        lines: List[str],
        tmpfile: str,
        task_vars: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Write lines to a remote temp file using ``tee`` and stdin.

        Writes content to a temporary file on the remote host, then
        applies ``chmod 0600`` for security.

        :param List[str] lines: Content lines to write
        :param str tmpfile: Temporary file path on remote host
        :param Optional[dict] task_vars: Ansible task variables
        :returns dict: Result from the ``tee`` command
        :raises RuntimeError: If writing or chmod fails
        """
        self._display.vvv(f"Writing to temp file: {tmpfile}")
        lines_str = "\n".join(lines)
        write_result = self._cmd(
            cmd=["tee", tmpfile],
            stdin=lines_str,
            task_vars=task_vars,
        )
        if write_result.get("rc", 1) != 0:
            raise RuntimeError(
                f"Failed to write temp file {tmpfile}: "
                f"{write_result.get('stderr', '')}"
            )

        self._display.vvv(f"Setting temp file permissions: {tmpfile}")
        chmod_result = self._cmd(
            ["chmod", "0600", tmpfile], task_vars=task_vars
        )
        if chmod_result.get("rc", 1) != 0:
            raise RuntimeError(
                f"Failed to chmod temp file: {chmod_result.get('stderr', '')}"
            )
        return write_result

    def _check_selinux_tools(
        self, perms: Dict[str, Any], task_vars: Dict[str, Any]
    ) -> bool:
        """
        Check whether SELinux tools are available if SELinux parameters
        are requested. Raises RuntimeError if required tools are
        missing.

        :param perms: dict of permission settings
        :param task_vars: Ansible task_vars
        :return: True if SELinux is in play, False otherwise
        """
        self._display.vvv("Checking for SELinux tools")
        selinux = any(
            perms and perms.get(k)
            for k in ("selevel", "serole", "setype", "seuser")
        )

        if not selinux:
            self._display.vvv("No SELinux tools found")
            return False

        chcon_path = self._which("chcon", task_vars=task_vars)
        semanage_path = self._which("semanage", task_vars=task_vars)
        self._display.vvv(
            f"SELinux check: chcon={chcon_path}, semanage={semanage_path}"
        )

        if not chcon_path:
            if not semanage_path:
                raise RuntimeError(
                    "SELinux parameters were specified, but both 'chcon' "
                    "and 'semanage' are missing on the remote host"
                )
            else:
                raise RuntimeError(
                    "SELinux requires 'chcon' to apply contexts, but it is "
                    "missing on the remote host"
                )

        if not semanage_path:
            host = self._get_inventory_hostname(task_vars)
            self._display.warning(
                f"[{host}] chcon is available but semanage is not — "
                "SELinux context changes may not persist"
            )

        return True

    def _convert_octal_mode_to_symbolic(
        self, octal_mode: Union[str, int]
    ) -> str:
        """
        Convert octal mode permissions to symbolic representation.

        Converts an octal representation of POSIX mode permissions into
        symbolic format without type or ACL symbols.

        :param Union[str, int] octal_mode: A stringable octal mode
            (e.g. 644, "0755")
        :returns str: String of the symbolic mode without type or ACL
            symbols
        :raises RuntimeError: On conversion error
        """
        int_mode = int(str(octal_mode), 8)
        try:
            # Strip type and ACL symbols
            symbolic_mode = stat.filemode(int_mode)[1:10]
        except Exception:
            raise RuntimeError(
                f"Error converting mode {octal_mode} to symbols"
            )
        return symbolic_mode

    def _compare_content_and_perms(
        self,
        dest: str,
        lines: List[str],
        perms: Optional[Dict[str, Any]] = None,
        selinux: bool = False,
        task_vars: Optional[Dict[str, Any]] = None,
    ) -> Tuple[bool, Optional[str], List[str]]:
        """
        Compare existing file contents and permissions to desired state.

        :param str dest: Path to destination file on the remote host
        :param List[str] lines: Desired content lines to compare
        :param Optional[dict] perms: Desired permissions dict (may
            include owner, group, mode, etc.)
        :param bool selinux: Whether SELinux attributes are in use
        :param Optional[dict] task_vars: Ansible task_vars from
            ``run()``
        :returns Tuple[bool, Optional[str], List[str]]: Tuple of
            (changed, old_content, old_lines)
        :raises RuntimeError: On invalid input
        """
        self._display.vvv(f"Comparing content and permissions with {dest}")
        changed = False

        old_stat = self._pseudo_stat(dest, task_vars=task_vars)
        self._display.vvv(f"Old stat: {old_stat}")

        if not old_stat["exists"]:
            self._display.vvv(f"File does not exist: {dest}")
            return True, None, []

        old_slurp = self._slurp(src=dest, task_vars=task_vars)
        old_content = old_slurp["content"]
        old_lines = old_slurp["content_lines"]
        self._display.vvv(f"Old lines: {old_lines}")

        if lines != old_lines:
            self._display.vvv("Content changed (lines comparison)")
            changed = True

        old_perms = self._get_perms(dest, selinux=selinux, task_vars=task_vars)
        self._display.vvv(f"Old perms: {old_perms}")

        if perms:
            for key in [
                "owner",
                "group",
                "selevel",
                "serole",
                "setype",
                "seuser",
            ]:
                if perms.get(key) and perms[key] != old_perms.get(key):
                    self._display.vvv(
                        f"Perm {key} changed: {perms[key]} != "
                        f"{old_perms.get(key)}"
                    )
                    changed = True

            if perms.get("mode"):
                try:
                    symbol_perms = self._convert_octal_mode_to_symbolic(
                        perms["mode"]
                    )
                    if symbol_perms != old_perms["mode"]:
                        self._display.vvv(
                            f"Mode changed: {symbol_perms} != "
                            f"{old_perms['mode']}"
                        )
                        changed = True
                except Exception as e:
                    raise RuntimeError(f"Invalid mode: {perms['mode']}: {e}")

        self._display.vvv(f"Comparison result: changed is {changed}")

        return changed, old_content, old_lines

    def _apply_perms_and_selinux(
        self,
        dest: str,
        perms: Dict[str, Any],
        selinux: bool = False,
        task_vars: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Apply ownership, permission mode, and SELinux context to file.

        Sets the owner, group, and file mode on the destination path if
        specified in ``perms``. Also applies the SELinux context if
        ``selinux`` is True. Then verifies the applied values match
        expectations.

        :param str dest: Remote file path to update
        :param dict perms: Dictionary with keys ``owner``, ``group``,
            ``mode``, etc.
        :param bool selinux: Boolean indicating whether SELinux handling
            is enabled
        :param Optional[dict] task_vars: Ansible task variables
        :raises RuntimeError: On failure to apply or verify any
            permission or SELinux step
        """
        self._display.vvv(f"Applying permissions to {dest}")
        cmd = self._cmd

        if perms:
            if perms.get("owner"):
                chown_result = cmd(
                    ["chown", perms["owner"], dest], task_vars=task_vars
                )
                if chown_result["rc"] != 0:
                    raise RuntimeError(
                        f"Failed to chown {dest}: "
                        f"{chown_result.get('stderr', '')}"
                    )

            if perms.get("group"):
                chgrp_result = cmd(
                    ["chgrp", perms["group"], dest], task_vars=task_vars
                )
                if chgrp_result["rc"] != 0:
                    raise RuntimeError(
                        f"Failed to chgrp {dest}: "
                        f"{chgrp_result.get('stderr', '')}"
                    )

            if perms.get("mode"):
                chmod_result = cmd(
                    ["chmod", perms["mode"], dest], task_vars=task_vars
                )
                if chmod_result["rc"] != 0:
                    raise RuntimeError(
                        f"Failed to chmod {dest}: "
                        f"{chmod_result.get('stderr', '')}"
                    )

        if selinux:
            self._handle_selinux_context(dest, perms, task_vars=task_vars)

        # Confirm permissions were applied
        if perms:
            final_perms = self._get_perms(
                dest, selinux=selinux, task_vars=task_vars
            )

            for key in [
                "owner",
                "group",
                "selevel",
                "serole",
                "setype",
                "seuser",
            ]:
                if perms.get(key) and final_perms.get(key) != perms.get(key):
                    raise RuntimeError(
                        f"Post-apply verification failed: expected {key}="
                        f"{perms[key]}, got {final_perms.get(key)}"
                    )

            if perms.get("mode"):
                try:
                    expected_mode = self._convert_octal_mode_to_symbolic(
                        perms["mode"]
                    )
                    actual_mode = final_perms.get("mode")
                    if actual_mode != expected_mode:
                        raise RuntimeError(
                            "Post-apply verification failed: expected mode="
                            f"{expected_mode}, got {actual_mode}"
                        )
                except Exception as e:
                    raise RuntimeError(
                        f"Invalid mode format: {perms['mode']}: {e}"
                    )

    def _make_raw_tmp_path(
        self, task_vars: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Create a temporary directory using raw shell fallback.

        Creates a temporary directory on the remote host using raw shell
        commands when standard Ansible temporary directory creation is
        not available.

        :param Optional[dict] task_vars: Ansible task variables
        :returns str: The path to the created temporary directory
        :raises RuntimeError: If directory creation fails
        """
        cmd = self._cmd
        shell = self._connection._shell
        task_vars = task_vars or {}

        if not shell.tmpdir:
            # Try to create a tmp dir like Ansible's default:
            # /tmp/ansible_xyz
            self._display.vvv("Creating temporary directory")
            tmp_path_cmd = ["mktemp", "-d", "/tmp/ansible.XXXXXX"]
            cmd_result = cmd(tmp_path_cmd, task_vars=task_vars)

            if cmd_result["rc"] != 0 or not cmd_result["stdout"]:
                raise RuntimeError(
                    "Failed to create temporary directory via raw fallback: "
                    f"{cmd_result['stderr']}"
                )

            tmpdir = cmd_result["stdout_lines"][0]
            shell.tmpdir = tmpdir  # Simulate Ansible's behavior

    def _write_file(
        self,
        content: Union[str, List[str]],
        dest: str,
        perms: Optional[Dict[str, Any]] = None,
        backup: bool = False,
        validate_cmd: Optional[str] = None,
        check_mode: Optional[bool] = None,
        task_vars: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Write content to destination file using fallback-compatible
        methods.

        Writes content to the destination file on the remote host with
        support for optional validation, backup creation, and
        permission handling.

        :param Union[str, List[str]] content: A string or list of
            strings to write
        :param str dest: The remote destination file path
        :param Optional[dict] perms: Dictionary with keys like owner,
            group, mode, seuser, etc.
        :param bool backup: Whether to back up the existing file
        :param Optional[str] validate_cmd: Shell command for validation,
            should include '%s'
        :param Optional[bool] check_mode: Whether to run in check mode
        :param Optional[dict] task_vars: Ansible task_vars from
            ``run()``
        :returns dict: Dictionary with 'changed', 'rc', 'msg', and
            optional 'backup_file'
        :raises RuntimeError: On any critical failure
        """
        self._display.vvv(f"Starting _write_file to {dest}")

        cmd = self._cmd
        shell = self._connection._shell
        backup_path = None
        check_mode = check_mode or False
        result = {"changed": False}

        self._make_raw_tmp_path(task_vars=task_vars)
        tmpdir = shell.tmpdir
        self._display.vvv(f"Using temporary directory: {tmpdir}")
        tmpfile = shell.join_path(tmpdir, "ansible_tmpfile")
        self._display.vvv(f"Using temporary file: {tmpfile}")

        old_stat = self._pseudo_stat(dest, task_vars=task_vars)
        self._display.vvv(f"Old stat: {old_stat}")
        if old_stat["exists"] and old_stat["type"] != "file":
            raise RuntimeError(f"Cannot write over {old_stat['type']}")

        # Normalize content and lines list
        lines, content = self._normalize_content(content)

        # Detect if any SELinux parameters are requested
        selinux = self._check_selinux_tools(perms, task_vars=task_vars)

        # Ensure the remote temporary directory exists
        self._mkdir(tmpdir, task_vars=task_vars, parents=True, mode="0700")

        # Write the lines to a temporary file
        self._write_temp_file(lines, tmpfile, task_vars=task_vars)

        # Run validation command, if provided
        if validate_cmd:
            self._validate_file(tmpfile, validate_cmd, task_vars=task_vars)

        # Back up the destination file, if requested
        if backup:
            backup_path = self._create_backup(dest, task_vars=task_vars)

        # Compare old and new
        changed, old_content, old_lines = self._compare_content_and_perms(
            dest, lines, perms, selinux, task_vars=task_vars
        )
        result["changed"] = changed

        # Calculate diff
        if task_vars.get("diff", False) and result["changed"]:
            diff = "\n".join(
                difflib.unified_diff(
                    old_lines, lines, fromfile=dest, tofile=dest, lineterm=""
                )
            )
            result["diff"] = {
                "before_header": dest,
                "after_header": dest,
                "before": old_content,
                "after": content,
                "unified_diff": diff,
            }
            self._display.vvv(f"Generated diff: {diff}")

        if check_mode:
            self._display.vvv("Check mode is enabled")
            if result["changed"]:
                result.update(
                    {"msg": "Check mode: changes would have been made."}
                )
            else:
                result.update({"msg": "Check mode: no changes needed."})

        else:
            if result["changed"]:
                # Move the temp file to the final destination
                mv_result = cmd(["mv", tmpfile, dest], task_vars=task_vars)
                self._display.vvv(f"mv result: {mv_result}")
                if mv_result["rc"] != 0:
                    raise RuntimeError(
                        "Failed to move temp file into place: "
                        f"{mv_result.get('stderr', '')}"
                    )

                # Apply final permissions and ownership
                self._apply_perms_and_selinux(
                    dest, perms, selinux, task_vars=task_vars
                )

                result["msg"] = "File written successfully"
            else:
                self._display.vvv("Files identical, no change necessary")
                result["msg"] = "File not changed"

        result["rc"] = 0

        if backup_path:
            result["backup_file"] = backup_path

        self._display.vvv(f"_write_file completed: {result}")
        return result

    def _mk_dest_dir(
        self, file_path: str, task_vars: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Create the parent directory of the target file if needed.

        Creates the parent directory of the target file if it does not
        exist.

        :param str file_path: The target file path
        :param Optional[dict] task_vars: Ansible task variables
        :returns dict: Dictionary with keys:
            - ``changed`` (bool): True if directory would be or was
              created
            - ``failed`` (bool): True if directory creation failed
              (only in non-check mode)
            - ``msg`` (str): Error message if applicable
        """
        self._display.vvv(f"Starting _mk_dest_dir ({file_path})")
        dir_path = path.dirname(file_path)
        dir_stat = self._pseudo_stat(dir_path, task_vars=task_vars)
        if not dir_stat["exists"]:
            if self._task.check_mode:
                self.result["changed"] = True
            else:
                try:
                    self._mkdir(dir_path, task_vars=task_vars)
                    self.result["changed"] = True
                except Exception as e:
                    self.result.update(
                        {
                            "rc": 256,
                            "msg": (
                                f"Error creating {dir_path} " f"({to_text(e)})"
                            ),
                            "failed": True,
                        }
                    )

    def _process_xattrs(
        self,
        source: Optional[object],
    ) -> Tuple[List[str], List[Dict[str, Any]], Optional[str]]:
        """Normalize xattr sources into names and specialised records.

        :param Optional[object] source: Extended attributes from xattr
            command
        :returns Tuple[List[str], List[Dict[str, Any]], Optional[str]]:
            Tuple of (attribute names, ACL records, SELinux value)
        """
        names: List[str] = []
        acl_records: Dict[str, Dict[str, Any]] = {}
        selinux_value: Optional[str] = None

        def place_acl(record_type: str) -> Dict[str, Any]:
            entry = acl_records.setdefault(record_type, {"type": record_type})
            return entry

        def handle(name: str, value: Optional[str]) -> None:
            nonlocal selinux_value
            key = name.strip()
            if not key:
                return
            lowered = key.lower()
            if lowered == "system.posix_acl_access":
                return
            if lowered == "system.posix_acl_default":
                return
            if lowered in {"com.apple.acl.text", "com.apple.security.acl"}:
                entry = place_acl("macos_xattr")
                if value is not None and "text" not in entry:
                    entry["text"] = value
                return
            if lowered in {"system.nfs4_acl", "nfs4_acl"}:
                entry = place_acl("nfs4_xattr")
                if value is not None and "text" not in entry:
                    entry["text"] = value
                return
            if lowered == "security.selinux":
                if value and selinux_value is None:
                    selinux_value = value
                return
            names.append(key)

        if isinstance(source, dict):
            for key, value in source.items():
                if isinstance(key, bytes):
                    key_obj = key.decode("utf-8", "ignore")
                else:
                    key_obj = str(key)
                value_str = None
                if value is not None:
                    if isinstance(value, bytes):
                        value_str = value.decode("utf-8", "ignore")
                    else:
                        value_str = str(value)
                handle(key_obj, value_str)
        elif isinstance(source, str):
            for line in source.splitlines():
                stripped = line.strip()
                if not stripped or stripped.startswith("#"):
                    continue
                if ":" in stripped and "=" not in stripped:
                    key, raw_val = stripped.split(":", 1)
                    handle(key, raw_val.strip())
                    continue
                if "=" in stripped:
                    key, raw_val = stripped.split("=", 1)
                    handle(key, raw_val.strip().strip('"').strip("'"))
                    continue
                handle(stripped, None)
        elif source is not None:
            handle(str(source), None)

        names = sorted(set(names))
        acl_list = [value for value in acl_records.values() if len(value) > 1]
        return names, acl_list, selinux_value

    def _merge_acl(self, info: Dict[str, Any], entry: Dict[str, Any]) -> None:
        """Merge ACL details into result dictionary with type tracking.

        :param Dict[str, Any] info: Stat dictionary to merge ACL into
        :param Dict[str, Any] entry: ACL entry to merge
        """
        if not entry:
            return

        entry_type = entry.get("type")
        existing = info.get("acl")

        if entry_type == "posix_xattr":
            if isinstance(existing, dict) and existing.get("type") == "posix":
                return
            if isinstance(existing, list) and any(
                isinstance(item, dict) and item.get("type") == "posix"
                for item in existing
            ):
                return

        if existing is None:
            info["acl"] = entry.copy()
            return

        if isinstance(existing, dict):
            existing_type = existing.get("type")
            if entry_type and existing_type == entry_type:
                merged = existing.copy()
                for key, value in entry.items():
                    if key in {"type"}:
                        continue
                    if key not in merged:
                        merged[key] = value
                info["acl"] = merged
                return

            info["acl"] = [existing.copy(), entry.copy()]
            return

        if isinstance(existing, list):
            if entry_type:
                for idx, item in enumerate(existing):
                    if (
                        isinstance(item, dict)
                        and item.get("type") == entry_type
                    ):
                        merged = item.copy()
                        for key, value in entry.items():
                            if key in {"type"}:
                                continue
                            if key not in merged:
                                merged[key] = value
                        existing[idx] = merged
                        info["acl"] = existing
                        return
            existing.append(entry.copy())
            info["acl"] = existing
            return

        # Existing value is plain string; convert to structured form.
        info["acl"] = [
            {"type": "unknown", "text": str(existing)},
            entry.copy(),
        ]

    def _extract_attr_flags(self, value: str) -> str:
        """Extract raw flag characters from lsattr output.

        Converts "--------------e-------" to "e" (just the set flags).
        For BSD/macOS format, returns empty string as it doesn't use
        single-character flags.

        :param str value: Raw lsattr/ls output
        :returns str: Flag characters that are set
        """
        flags_str = value.strip()
        if not flags_str or flags_str == "-":
            return ""

        # BSD/macOS format - doesn't use attr_flags field
        if "," in flags_str or any(
            word.isalpha() and len(word) > 1 for word in flags_str.split()
        ):
            return ""

        # Linux lsattr format - extract non-dash characters
        flag_chars = "".join(
            char for char in flags_str if char not in ("-", " ")
        )
        return flag_chars

    def _normalize_flags(self, value: str) -> List[str]:
        """Parse filesystem flags into attribute names.

        Handles multiple formats:
        - Linux lsattr: "--------------e-------" → ["extents"]
        - BSD/macOS: "restricted,hidden" or "restricted hidden" → as-is

        :param str value: Raw flags string
        :returns List[str]: List of attribute names
        """
        flags_str = value.strip()
        if not flags_str or flags_str == "-":
            return []

        # BSD/macOS format: comma or space separated words
        if "," in flags_str:
            return [
                flag.strip() for flag in flags_str.split(",") if flag.strip()
            ]

        # Check if readable words (BSD format without commas)
        if any(word.isalpha() and len(word) > 1 for word in flags_str.split()):
            return [flag.strip() for flag in flags_str.split() if flag.strip()]

        # Linux lsattr format: single-character flags
        flag_map = {
            "a": "append_only",
            "c": "compressed",
            "d": "no_dump",
            "e": "extents",
            "i": "immutable",
            "j": "data_journaling",
            "s": "secure_deletion",
            "t": "no_tail_merging",
            "u": "undeletable",
            "A": "no_atime",
            "D": "synchronous_directory",
            "S": "synchronous_updates",
            "T": "top_of_directory_hierarchy",
            "C": "no_copy_on_write",
            "E": "encrypted",
            "I": "indexed_directory",
            "N": "inline_data",
            "P": "project_hierarchy",
            "V": "verity",
        }

        attributes = []
        for char in flags_str:
            if char in flag_map:
                attributes.append(flag_map[char])

        return attributes

    def _get_acl(
        self, path: str, task_vars: Optional[Dict[str, Any]]
    ) -> Optional[Dict[str, Any]]:
        """Retrieve ACL information for a path.

        :param str path: Path to get ACLs for
        :param Optional[Dict[str, Any]] task_vars: Available Ansible
            variables
        :returns Optional[Dict[str, Any]]: ACL metadata with type or None
        """
        result = self._cmd(["getfacl", "-p", path], task_vars=task_vars)
        if result.get("rc") == 0:
            output = (result.get("stdout") or "").strip()
            if output:
                return {"type": "posix", "text": output}
        # macOS fallback: ls -le prints ACLs
        alt = self._cmd(["ls", "-le", path], task_vars=task_vars)
        if alt.get("rc") == 0:
            output = (alt.get("stdout") or "").strip()
            if output:
                lines = output.splitlines()
                prefixes = tuple(f"{i}:" for i in range(10))
                if any(
                    line.lstrip().startswith(prefixes) for line in lines[1:]
                ):
                    return {"type": "macos", "text": output}
        return None

    def _get_xattrs(
        self, path: str, task_vars: Optional[Dict[str, Any]]
    ) -> Optional[str]:
        """Retrieve extended attributes for a path.

        :param str path: Path to get extended attributes for
        :param Optional[Dict[str, Any]] task_vars: Available Ansible
            variables
        :returns Optional[str]: Extended attributes or None if
            unavailable
        """
        result = self._cmd(
            ["getfattr", "--absolute-names", "-d", path], task_vars=task_vars
        )
        if result.get("rc") == 0:
            output = (result.get("stdout") or "").strip()
            if output:
                return output
        # macOS fallback: xattr -l
        alt = self._cmd(["xattr", "-l", path], task_vars=task_vars)
        if alt.get("rc") == 0:
            output = (alt.get("stdout") or "").strip()
            if output:
                return output
        return None

    def _get_flags(
        self, path: str, task_vars: Optional[Dict[str, Any]]
    ) -> Optional[str]:
        """Retrieve filesystem flags for a path.

        :param str path: Path to get flags for
        :param Optional[Dict[str, Any]] task_vars: Available Ansible
            variables
        :returns Optional[str]: Filesystem flags or None if unavailable
        """
        result = self._cmd(["lsattr", "-d", path], task_vars=task_vars)
        if result.get("rc") != 0:
            alt = self._cmd(["ls", "-ldO", path], task_vars=task_vars)
            if alt.get("rc") != 0:
                return None
            stdout = alt.get("stdout") or ""
            parts = stdout.split()
            if len(parts) >= 5:
                flags = parts[4]
                if flags != "-":
                    return flags
            return None
        stdout = result.get("stdout") or ""
        parts = stdout.split()
        if not parts:
            return None
        return parts[0]
