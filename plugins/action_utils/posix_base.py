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
manually invoke other action plugins (e.g. command, slurp64) using FQCNs.
Used by custom action plugins to gracefully degrade to raw execution
when Python is not available on the remote host.
"""

from ansible.errors import AnsibleError
from ansible.plugins.action import ActionBase
from datetime import datetime, timezone
import hashlib
import shlex


class PosixBase(ActionBase):
    """
    Base class for POSIX-compatible Ansible action plugins with raw
    fallback support.

    This class extends `ActionBase` and provides shared helpers for
    action plugins that must operate on remote hosts without a working
    Python interpreter.

    It implements fallback-compatible versions of common file and shell
    operations, including command execution, file slurping, directory
    creation, and secure file writing with backup, validation, and
    SELinux support. It also enables inter-plugin delegation using fully
    qualified collection names (FQCNs).

    This base is intended for use in collections targeting POSIX systems.
    All operations rely exclusively on POSIX-standard tools such as
    `cat`, `mv`, `cp`, `mkdir`, `chown`, `chmod`, and `printf`. Non-
    portable utilities like `install` are deliberately avoided.

    Usage:
        class ActionModule(PosixBase):
            def run(self, tmp=None, task_vars=None):
                ...
    """

    def run(self, tmp=None, task_vars=None):
        """
        Base run method that initializes the result structure but must
        be extended by subclasses.

        This replaces the NotImplementedError with a minimal
        implementation so that child classes can safely call
        super().run() to get a standard results dict.

        :param tmp: Temporary path (optional)
        :param task_vars: Task variables dict
        :return: Initial results dictionary
        """
        return super().run(tmp, task_vars)

    def _is_interpreter_missing(self, result):
        """
        Check if failure was likely caused by a missing Python
        interpreter.

        :param result: A result dict from _execute_module or fallback
                       command.
        :return: True if failure likely due to missing Python, else
                 False.
        """
        if not isinstance(result, dict):
            return False

        if result.get('rc') != 127:
            return False

        stderr = result.get('module_stderr', '')
        keywords = (
            'python: command not found',
            'no such file or directory',
            'bad interpreter',
            "can't open",
        )

        return any(kw in stderr.lower() for kw in keywords)

    def _run_action(
        self, plugin_name, plugin_args, task_vars=None, check_mode: bool = None
    ):
        """
        Execute another action plugin using the provided arguments.

        :param plugin_name: Fully qualified name of the plugin to run
                            (e.g. 'ansible.builtin.command').
        :param plugin_args: Dictionary of arguments to pass to the
                            plugin.
        :param task_vars: Dictionary of task variables from the calling
                          task.
        :return: The result dictionary returned by the plugin's run
                 method.
        """
        current_fqcn = self._task.action.lower().strip()
        requested_fqcn = plugin_name.lower().strip()

        if requested_fqcn == current_fqcn:
            raise AnsibleError(
                f"CompatAction attempted to call '{plugin_name}' from within "
                f"itself. This would result in infinite recursion."
            )

        task = self._task.copy()
        task.args.clear()
        task.args.update(plugin_args)

        if check_mode is not None:
            task.check_mode = check_mode

        if "_force_raw" in self._task.args:
            task.args["_force_raw"] = self._task.args["_force_raw"]

        plugin = self._shared_loader_obj.action_loader.get(
            plugin_name,
            task=task,
            connection=self._connection,
            play_context=self._play_context,
            loader=self._loader,
            templar=self._templar,
            shared_loader_obj=self._shared_loader_obj,
        )

        return plugin.run(task_vars=task_vars or {})

    def _cmd(self, argv, task_vars=None, check_mode: bool = None):
        """
        Run the fallback-compatible 'command' action plugin with arguments.

        :param argv: List of command arguments to execute.
        :param task_vars: Dictionary of task variables from the calling task.
        :param check_mode: Optional override for Ansible check mode.
        :return: The result dictionary from the command plugin.
        """
        return self._run_action(
            'o0_o.posix.command',
            {'argv': argv},
            task_vars,
            check_mode=check_mode,
        )

    def _slurp(self, src, task_vars=None):
        """
        Run the fallback-compatible 'slurp64' action plugin to read
        remote files.

        :param src: The path to the file to slurp on the remote host.
        :param task_vars: Dictionary of task variables from the calling
                          task.
        :return: The result dictionary from the slurp64 plugin.
        """
        return self._run_action(
            'o0_o.posix.slurp64',
            {'src': src},
            task_vars,
        )

    def _cat(self, src, task_vars=None):
        """
        Fallback method to read the contents of a file using 'cat'.

        :param src: Path to the file on the remote host.
        :param task_vars: Dictionary of task variables from the calling
                          task.
        :return: Dictionary with read results or error.
        """
        result = self._cmd(['cat', src], task_vars, False)
        result['changed'] = False
        result['source'] = src

        stdout = result.pop('stdout', None)
        stderr = result.pop('stderr', None)
        result.pop('stdout_lines', None)
        result.pop('stderr_lines', None)

        if result.pop('rc', 0) != 0:
            result['failed'] = True
            result['msg'] = stderr.strip() or stdout.strip()
        else:
            result['content'] = stdout.replace('\r', '')

        result['raw'] = True
        return result

    def _mkdir(self, path, task_vars=None, parents=True, mode=None):
        """
        Ensure a directory exists on the remote host, optionally
        applying a permission mode, using fallback-compatible methods.

        :param path: The remote directory path to create
        :param task_vars: Ansible task_vars from run()
        :param parents: Whether to create parent directories
                        (`mkdir -p`)
        :param mode: Optional permission mode string (e.g. "0755")
        :returns: dict with {'changed': bool, 'rc': int}
        :raises: AnsibleError on error
        """
        cmd = self._cmd

        # Check if the path exists
        test_exists = cmd(["test", "-e", path], task_vars)
        if test_exists["rc"] == 0:
            test_dir = cmd(["test", "-d", path], task_vars)
            if test_dir["rc"] == 0:
                return {"changed": False, "rc": 0}
            raise AnsibleError(f"Path '{path}' exists but is not a directory")

        # Attempt to create directory
        args = ["mkdir"]
        if parents:
            args.append("-p")
        if mode:
            args.extend(["-m", mode])
        args.append(path)

        mkdir_result = cmd(args, task_vars)
        if mkdir_result["rc"] != 0:
            raise AnsibleError(
                f"Failed to create directory '{path}': "
                f"{mkdir_result.get('stderr', '').strip()}"
            )

        return {"changed": True, "rc": 0}

    def _quote(self, s):
        """
        Quote a string for safe use in shell commands on the remote host.

        This method uses the remote connection's shell quoting logic if
        available (e.g., for non-POSIX shells), falling back to Python's
        `shlex.quote()` for standard POSIX-compatible escaping.

        :param s: the string to quote
        :return: the safely quoted string
        """
        shell = self._connection._shell
        return getattr(shell, "quote", shlex.quote)(s)

    def _generate_ansible_backup_path(self, path):
        """
        Generate an Ansible-style backup file name based on the path.

        The format is: <path>.<md5_digest>.<UTC timestamp>

        :param path: The full remote file path to back up.
        :return: Backup file name as a string.
        """
        digest = hashlib.md5(path.encode("utf-8")).hexdigest()
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        return f"{path}.{digest}.{timestamp}"

    def _validate_file(self, tmpfile, validate_cmd, task_vars=None):
        """
        Run a validation command against a temporary file.

        :param tmpfile: the temporary file to validate
        :param validate_cmd: the validation command template
        :param task_vars: task vars from the calling action
        :raises: AnsibleError if validation fails
        """
        if not validate_cmd:
            return

        shell = self._action._connection._shell
        cmd = validate_cmd % self._quote(tmpfile)
        result = self._cmd(cmd, task_vars)

        if result['rc'] != 0:
            raise AnsibleError(
                f"Validation failed: {validate_cmd} => "
                f"{result.get('stderr', '')}"
            )

    def _create_backup(self, dest, task_vars=None):
        """
        Create a backup of the destination file if it exists.

        :param dest: destination file to back up
        :param task_vars: task vars from the calling action
        :returns: path to the backup file or None if not created
        :raises: AnsibleError if backup fails
        """
        result = self._cmd(["test", "-e", dest], task_vars)
        if result['rc'] != 0:
            return None

        backup_path = self._generate_ansible_backup_path(dest)
        result = self._cmd(
            ["cp", "--preserve=all", dest, backup_path], task_vars
        )

        if result['rc'] != 0:
            raise AnsibleError(f"Backup failed: {result.get('stderr', '')}")

        return backup_path

    def _handle_selinux_context(self, dest, perms, task_vars=None):
        """
        Apply SELinux context to the destination file.

        If both 'semanage' and 'restorecon' are available, persist the context
        via semanage and apply it with restorecon. Otherwise, fall back to
        chcon.

        :param dest: Target file path on the remote host
        :param perms: Dict of SELinux keys (seuser, serole, setype, selevel)
        :param task_vars: Ansible task_vars from the calling context
        :raises: AnsibleError if context application fails
        """
        if not perms:
            return

        selinux_keys = [
            k for k in ("selevel", "serole", "setype", "seuser")
            if perms.get(k)
        ]
        if not selinux_keys:
            return

        setype = perms.get("setype")
        seuser = perms.get("seuser")
        serole = perms.get("serole")
        selevel = perms.get("selevel")

        # Try semanage if available and setype is defined
        semanage_path = self._which("semanage", task_vars)
        restorecon_path = self._which("restorecon", task_vars)

        if semanage_path and restorecon_path and setype:
            fcontext_type = setype
            semanage_cmd = [
                "semanage", "fcontext", "-a",
                "-t", fcontext_type,
                dest
            ]
            result = self._cmd(semanage_cmd, task_vars)
            if result["rc"] != 0:
                raise AnsibleError(
                    f"Failed to register SELinux context with semanage: "
                    f"{result.get('stderr', '')}"
                )

            restorecon_cmd = ["restorecon", dest]
            result = self._cmd(restorecon_cmd, task_vars)
            if result["rc"] != 0:
                raise AnsibleError(
                    f"Failed to apply SELinux context with restorecon: "
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

        result = self._cmd(chcon_cmd, task_vars)
        if result["rc"] != 0:
            raise AnsibleError(
                f"Failed to set SELinux context with chcon: "
                f"{result.get('stderr', '')}"
            )

    def _which(self, binary, task_vars):
        """
        Locate the full path of a binary using POSIX-compliant methods.

        Attempts to resolve the path to an executable by first using the
        POSIX-compliant `command -v`, and falls back to `which` if necessary.
        If the binary is a shell builtin or function, returns its name.

        Args:
            binary (str): The name of the binary to locate (e.g., 'chcon').
            task_vars (dict): Ansible task variables passed to the _cmd method.

        Returns:
            str or None: Path to the binary or the name if it's a shell
                         builtin.
        """
        # POSIX-compliant check first
        cmd_result = self._cmd(["sh", "-c", f"command -v {binary}"], task_vars)
        stdout = cmd_result.get("stdout", "").strip()

        if cmd_result["rc"] == 0 and stdout:
            # If stdout is just the binary name (no slash), assume builtin
            if "/" not in stdout:
                return binary
            return stdout

        # Fallback to 'which' if available
        cmd_result = self._cmd(["which", binary], task_vars)
        stdout = cmd_result.get("stdout", "").strip().lower()

        if cmd_result["rc"] == 0 and stdout:
            # Detect builtin shell descriptions from common formats
            if "shell built-in command" in stdout or "shell builtin" in stdout:
                return binary
            if stdout and "/" not in stdout:
                return binary
            return stdout

        return None

    def _write_file(
        self,
        content,
        dest,
        task_vars=None,
        perms=None,
        backup=False,
        validate_cmd=None
    ):
        """
        Write content to the destination file on the remote host using
        fallback-compatible methods. Also supports optional validation,
        backup creation, and permission handling.

        :param content: a string or a list of strings to write
        :param dest: the remote destination file path
        :param task_vars: Ansible task_vars from run()
        :param perms: dict with keys like owner, group, mode, seuser, etc.
        :param backup: whether to back up the existing file
        :param validate_cmd: shell command for validation, should include '%s'
        :return: dict with 'changed', 'rc', 'msg', and optional 'backup_file'
        :raises: AnsibleError on any critical failure
        """
        cmd = self._cmd
        shell = self._connection._shell
        changed = False
        backup_path = None

        tmpdir = shell.tmpdir
        tmpfile = shell.join_path(tmpdir, "ansible_tmpfile")

        # Normalize content to a list of strings
        if isinstance(content, str):
            lines = content.splitlines()
        elif isinstance(content, list):
            if not all(isinstance(line, (str, int, float)) for line in content):
                raise AnsibleError("_write_file() requires strings or numbers")
            lines = [str(line) for line in content]
        else:
            raise AnsibleError(
                "_write_file() requires a string or list of strings"
            )

        # Detect if any SELinux parameters are requested
        selinux = any(
            perms and perms.get(k)
            for k in ("selevel", "serole", "setype", "seuser")
        )

        # Check SELinux tools if needed
        if selinux:
            chcon_path = self._which("chcon", task_vars)
            semanage_path = self._which("semanage", task_vars)

            if not chcon_path:
                if not semanage_path:
                    raise AnsibleError(
                        "SELinux parameters were specified, but both 'chcon' "
                        "and 'semanage' are missing on the remote host"
                    )
                else:
                    raise AnsibleError(
                        "SELinux requires 'chcon' to apply contexts, but it "
                        "is missing on the remote host"
                    )
            elif not semanage_path:
                self._display.warning(
                    "chcon is available but semanage is not — SELinux context "
                    "changes may not persist"
                )

        # Ensure the remote temporary directory exists
        self._mkdir(tmpdir, task_vars, parents=True, mode="0700")

        # Write the lines to a temporary file using printf
        quoted_lines = " ".join(self._quote(line) for line in lines)
        printf_cmd = (
            f"printf '%s\\n' {quoted_lines} > {self._quote(tmpfile)}"
        )
        printf_result = self._action._low_level_execute_command(printf_cmd)

        if printf_result["rc"] != 0:
            raise AnsibleError(
                f"Failed to write temp file {tmpfile}: "
                f"{printf_result.get('stderr', '')}"
            )

        # Lock down temp file with strict permissions
        chmod_result = cmd(["chmod", "0600", tmpfile], task_vars)
        if chmod_result["rc"] != 0:
            raise AnsibleError(
                f"Failed to chmod temp file: "
                f"{chmod_result.get('stderr', '')}"
            )

        # Run validation command, if provided
        if validate_cmd:
            self._validate_file(tmpfile, validate_cmd, task_vars)

        # Back up the destination file, if requested
        if backup:
            backup_path = self._create_backup(dest, task_vars)

        # Move the temp file to the final destination
        mv_result = cmd(["mv", tmpfile, dest], task_vars)
        if mv_result["rc"] != 0:
            raise AnsibleError(
                f"Failed to move temp file into place: "
                f"{mv_result.get('stderr', '')}"
            )
        changed = True

        # Apply final permissions and ownership
        if perms:
            if perms.get("owner"):
                chown_result = cmd(["chown", perms["owner"], dest], task_vars)
                if chown_result["rc"] != 0:
                    raise AnsibleError(
                        f"Failed to chown {dest}: "
                        f"{chown_result.get('stderr', '')}"
                    )

            if perms.get("group"):
                chgrp_result = cmd(["chgrp", perms["group"], dest], task_vars)
                if chgrp_result["rc"] != 0:
                    raise AnsibleError(
                        f"Failed to chgrp {dest}: "
                        f"{chgrp_result.get('stderr', '')}"
                    )

            if perms.get("mode"):
                chmod_result = cmd(["chmod", perms["mode"], dest], task_vars)
                if chmod_result["rc"] != 0:
                    raise AnsibleError(
                        f"Failed to chmod {dest}: "
                        f"{chmod_result.get('stderr', '')}"
                    )

        # Apply SELinux context if requested
        if selinux:
            self._handle_selinux_context(dest, perms, task_vars)

        # Return result dictionary
        result = {
            "changed": changed,
            "rc": 0,
            "msg": "File written successfully"
        }

        if backup_path:
            result["backup_file"] = backup_path

        return result
