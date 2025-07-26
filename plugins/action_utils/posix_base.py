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
from ansible.module_utils.common.text.converters import to_text
from datetime import datetime, timezone
from os import path
import stat
import hashlib
import shlex
import difflib


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
        :return: True if failure likely due to missing Python, else False.
        """
        if not isinstance(result, dict):
            return False

        if result.get('rc') != 127:
            return False

        msg = result.get('msg', '')
        if not isinstance(msg, str):
            return False

        canary_str = (
            'The module failed to execute correctly, you probably need to set '
            'the interpreter'
        )

        if canary_str.lower() in msg.lower():
            self.force_raw = True
            self._display.vv('Python not found, proceeding with raw commands')
            return True

        return False

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
                'itself. This would result in infinite recursion.'
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

        if check_mode is not None:
            plugin._task.check_mode = check_mode

        result = plugin.run(task_vars=task_vars)

        if result['raw']:
            self.force_raw = True

        return result

    def _cmd(self, cmd, stdin=None, task_vars=None, check_mode: bool = None):
        """
        Run the fallback-compatible 'command' action plugin with arguments.

        :param cmd: Command to execute. Can be a shell string or a list of
                    arguments.
        :param stdin: Optional standard input to pass to the command.
        :param task_vars: Dictionary of task variables from the calling task.
        :param check_mode: Optional override for Ansible check mode.
        :return: The result dictionary from the command plugin.
        """
        task_vars = task_vars or {}

        args = {'stdin': stdin}

        if isinstance(cmd, list):
            args['argv'] = cmd
        elif isinstance(cmd, str):
            args['cmd'] = cmd
        else:
            raise TypeError(
                f"Expected cmd to be str or list, got {type(cmd).__name__}"
            )

        return self._run_action(
            'o0_o.posix.command',
            args,
            task_vars=task_vars,
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
            task_vars=task_vars,
        )

    def _cat(self, src, task_vars=None):
        """
        Fallback method to read the contents of a file using 'cat'.

        :param src: Path to the file on the remote host.
        :param task_vars: Dictionary of task variables from the calling
                          task.
        :return: Dictionary with read results or error.
        """
        cmd_result = self._cmd(
            ['cat', src],
            task_vars=task_vars,
            check_mode=False
        )
        results = {'changed': False, 'raw': cmd_result.get('raw', False)}
        results['source'] = src

        stdout = cmd_result.pop('stdout', None)
        stderr = cmd_result.pop('stderr', None)

        if cmd_result.get('rc') != 0:
            results['failed'] = True
            results['msg'] = stderr.strip() or stdout.strip()
        else:
            results['content'] = stdout.replace('\r', '')

        return results

    def _sanitize_args(self, args):
        """
        Return a copy of the argument dictionary with all keys that have a
        value of None removed.

        This is useful when passing arguments to Ansible modules that enforce
        mutually exclusive parameters or expect missing values to be omitted
        rather than explicitly set to null/None.

        :param args: Dictionary of module arguments to sanitize.
        :type args: dict
        :return: A new dictionary with all None values removed.
        :rtype: dict
        """
        return {k: v for k, v in args.items() if v is not None}

    def _pseudo_stat(self, target_path, task_vars=None):
        """
        Fallback-compatible file stat using POSIX `test` commands.

        This method uses a combination of `test` shell commands to detect
        if a remote path exists, what type of object it is (e.g., file,
        directory, etc.), and whether it is a symlink.

        :param target_path: The remote path to test.
        :param task_vars: Ansible task_vars from run(), passed to _cmd().
        :returns:
            dict: {
                "exists": bool,     # Whether the target exists.
                "type": str or None,  # POSIX type, one of: file,
                                      # directory, block, char, pipe,
                                      # socket. None if nonexistent.
                "symlink": bool,    # True if the path is a symbolic link.
                "raw": bool,        # True if fallback (raw) logic was used.
            }
        :raises: AnsibleError if type cannot be determined.
        """
        exists_test = self._cmd(
            ["test", "-e", target_path], task_vars=task_vars, check_mode=False
        )

        result = {'raw': exists_test.get("raw", False)}

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
                check_mode=False
            )
            if check["rc"] == 0:
                result["type"] = type_name
                return result

        raise AnsibleError(
            f"All POSIX 'test' commands failed on '{target_path}'"
        )

    def _mkdir(self, target_path, task_vars=None, parents=True, mode=None):
        """
        Ensure a directory exists on the remote host, optionally applying a
        permission mode, using fallback-compatible methods.

        :param target_path: The remote directory path to create
        :param task_vars: Ansible task_vars from run()
        :param parents: Whether to create parent directories (`mkdir -p`)
        :param mode: Optional permission mode string (e.g. "0755")
        :returns: dict with {'changed': bool}
        :raises: AnsibleError on error
        """
        self._display.vvv(f"Creating directory: {target_path}")

        # Check if the path exists
        stat = self._pseudo_stat(target_path, task_vars=task_vars)
        if stat["type"] == "directory":
            self._display.vvv(f"Directory already exists: {target_path}")
            return {"rc": 0, "changed": False}
        if stat["exists"]:
            raise AnsibleError(
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

        mkdir_results = self._cmd(args, task_vars=task_vars)
        if mkdir_results["rc"] != 0:
            raise AnsibleError(
                f"Failed to create directory '{target_path}': "
                f"{mkdir_results.get('stderr', '').strip()}"
            )

        return {"rc": mkdir_results["rc"], "changed": True, "raw": stat["raw"]}

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

    def _generate_ansible_backup_path(self, target_path):
        """
        Generate an Ansible-style backup file name based on the path.

        The format is: <path>.<md5_digest>.<UTC timestamp>

        :param path: The full remote file path to back up.
        :return: Backup file name as a string.
        """
        digest = hashlib.md5(target_path.encode("utf-8")).hexdigest()
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        return f"{target_path}.{digest}.{timestamp}"

    def _validate_file(self, tmpfile, validate_cmd, task_vars=None):
        """
        Run a validation command against a temporary file.

        :param tmpfile: the temporary file to validate
        :param validate_cmd: the validation command template
        :param task_vars: task vars from the calling action
        :raises: AnsibleError if validation fails
        """
        self._display.vvv(f"Validating {tmpfile}")
        if not validate_cmd:
            return

        shell = self._connection._shell
        cmd = validate_cmd % self._quote(tmpfile)
        result = self._cmd(cmd, task_vars=task_vars)

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
        result = self._cmd(["test", "-e", dest], task_vars=task_vars)
        if result['rc'] != 0:
            return None

        backup_path = self._generate_ansible_backup_path(dest)
        self._display.vvv(f"Creating backup at {backup_path}")
        result = self._cmd(
            ["cp", "--preserve=all", dest, backup_path], task_vars=task_vars
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
        self._display.vvv(f"Handling SELinux for {dest}")
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
        semanage_path = self._which("semanage", task_vars=task_vars)
        restorecon_path = self._which("restorecon", task_vars=task_vars)

        if semanage_path and restorecon_path and setype:
            fcontext_type = setype
            semanage_cmd = [
                "semanage", "fcontext", "-a",
                "-t", fcontext_type,
                dest
            ]
            result = self._cmd(semanage_cmd, task_vars=task_vars)
            if result["rc"] != 0:
                raise AnsibleError(
                    'Failed to register SELinux context with semanage: '
                    f"{result.get('stderr', '')}"
                )

            restorecon_cmd = ["restorecon", dest]
            result = self._cmd(restorecon_cmd, task_vars=task_vars)
            if result["rc"] != 0:
                raise AnsibleError(
                    'Failed to apply SELinux context with restorecon: '
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
            raise AnsibleError(
                'Failed to set SELinux context with chcon: '
                f"{result.get('stderr', '')}"
            )

    def _which(self, binary, task_vars=None):
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
        cmd_result = self._cmd(
            ["sh", "-c", f"command -v {binary}"], task_vars=task_vars
        )
        stdout = cmd_result.get("stdout", "").strip()

        if cmd_result["rc"] == 0 and stdout:
            # If stdout is just the binary name (no slash), assume builtin
            if "/" not in stdout:
                return binary
            return stdout

        # Fallback to 'which' if available
        cmd_result = self._cmd(["which", binary], task_vars=task_vars)
        stdout = cmd_result.get("stdout", "").strip().lower()

        if cmd_result["rc"] == 0 and stdout:
            # Detect builtin shell descriptions from common formats
            if "shell built-in command" in stdout or "shell builtin" in stdout:
                return binary
            if stdout and "/" not in stdout:
                return binary
            return stdout

        return None

    def _get_perms(self, target, selinux=False, task_vars=None):
        """
        Retrieve POSIX file permissions (and optionally SELinux context)
        for a given file or directory using `ls`.

        When `selinux=True`, the SELinux context (if available) is also
        parsed and returned alongside mode, owner, and group. Any trailing
        ACL/attribute indicators (e.g., '+', '@') are stripped from the
        mode field.

        Args:
            target (str): Path to the file or directory to inspect.
            task_vars (dict): Ansible task variables for command execution.
            selinux (bool): Whether to include SELinux context information.

        Returns:
            dict: {
                'mode' (str): Symbolic file mode (e.g., '-rw-r--r--'),
                'owner' (str): File owner,
                'group' (str): File group,
                Optional SELinux keys:
                    'seuser' (str): SELinux user,
                    'setype' (str): SELinux type,
                    'serole' (str): SELinux role,
                    'selevel' (str): SELinux level
            }

        Raises:
            AnsibleError: If the `ls` command fails or produces unexpected output.
        """
        self._display.vvv(f"Getting permissions of {target}")
        ls_args = ["ls"]
        if selinux:
            ls_args.append("-Zd")
        else:
            ls_args.append("-ld")
        ls_args.append(target)

        cmd_results = self._cmd(ls_args, task_vars=task_vars)
        if cmd_results["rc"] != 0:
            raise AnsibleError(f"Could not stat {target}: {cmd_results['stderr']}")

        parts = cmd_results["stdout_lines"][0].split()

        if selinux:
            try:
                # Format: context user:role:type:level owner group ...
                context = parts[0]
                mode = parts[1][1:10]  # Trim type and ACL symbols
                owner = parts[2]
                group = parts[3]
                seuser, serole, setype, selevel = context.split(":")
            except Exception:
                raise AnsibleError(
                    "Unexpected SELinux output from ls -Zd: "
                    f"{cmd_results['stdout']}"
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

    def _normalize_content(self, content):
        """
        Normalize input content to a list of lines and a
        newline-terminated string.

        Accepts either a string or a list of strings/numbers. Ensures the
        output string ends with a newline character and all list elements are
        converted to strings. Raises an AnsibleError on unsupported input
        types.

        :param content: The input to normalize (str or list of str/int/float)
        :return: Tuple (lines: List[str], content: str)
        :raises: AnsibleError if input is of invalid type or contains
                 non-stringlike items
        """
        if isinstance(content, str):
            lines = content.splitlines()
            normalized = content if content.endswith("\n") else content + "\n"
        elif isinstance(content, list):
            if not all(
                isinstance(line, (str, int, float)) for line in content
            ):
                raise AnsibleError("_write_file() requires strings or numbers")
            lines = [str(line) for line in content]
            normalized = '\n'.join(lines) + '\n'
        else:
            raise AnsibleError(
                "_write_file() requires a string or list of strings"
            )
        self._display.vvv(f"Normalized lines: {lines}")
        return lines, normalized

    def _write_temp_file(self, lines, tmpfile, task_vars=None):
        """
        Write lines to a remote temp file using `tee` and stdin,
        then chmod it to 0600.
        """
        self._display.vvv(f"Writing to temp file: {tmpfile}")
        lines_str = "\n".join(lines)
        write_result = self._cmd(
            cmd=['tee', tmpfile],
            stdin=lines_str,
            task_vars=task_vars,
        )
        if write_result.get("rc", 1) != 0:
            raise AnsibleError(
                f"Failed to write temp file {tmpfile}: "
                f"{write_result.get('stderr', '')}"
            )

        self._display.vvv(f"Setting temp file permissions: {tmpfile}")
        chmod_result = self._cmd(
            ["chmod", "0600", tmpfile], task_vars=task_vars
        )
        if chmod_result.get("rc", 1) != 0:
            raise AnsibleError(
                f"Failed to chmod temp file: {chmod_result.get('stderr', '')}"
            )
        return write_result

    def _check_selinux_tools(self, perms, task_vars):
        """
        Check whether SELinux tools are available if SELinux parameters
        are requested. Raises AnsibleError if required tools are missing.

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
                raise AnsibleError(
                    "SELinux parameters were specified, but both 'chcon' "
                    "and 'semanage' are missing on the remote host"
                )
            else:
                raise AnsibleError(
                    "SELinux requires 'chcon' to apply contexts, but it is "
                    "missing on the remote host"
                )

        if not semanage_path:
            self._display.warning(
                "chcon is available but semanage is not — SELinux context "
                "changes may not persist"
            )

        return True

    def _convert_octal_mode_to_symbolic(self, octal_mode):
        """
        Convert an octal representation of POSIX mode permissions into symbols.

        :param octal_mode: A stringable octal mode (e.g. 644, '0755')
        :return: String of the symbolic mode without type or ACL symbols
        :raises: AnsibleError on conversion error
        """
        int_mode = int(str(octal_mode), 8)
        try:
            # Strip type and ACL symbols
            symbolic_mode = stat.filemode(int_mode)[1:10]
        except Exception as e:
            raise AnsibleError(
                f"Error converting mode {octal_mode} to symbols"
            )
        return symbolic_mode

    def _compare_content_and_perms(
        self,
        dest,
        lines,
        perms=None,
        selinux=False,
        task_vars=None,
    ):
        """
        Compare existing file contents and permissions to the desired state.

        :param dest: Path to destination file on the remote host
        :param lines: Desired content lines to compare
        :param perms: Desired permissions dict (may include owner, group, mode, etc.)
        :param selinux: Whether SELinux attributes are in use
        :param task_vars: Ansible task_vars from run()
        :return: Tuple of (changed: bool, old_content: str, old_lines: List[str])
        :raises: AnsibleError on invalid input
        """
        self._display.vvv(f"Comparing content and permissions with {dest}")
        changed = False

        old_stat = self._pseudo_stat(dest, task_vars=task_vars)
        self._display.vvv(f"Old stat: {old_stat}")

        if not old_stat['exists']:
            self._display.vvv(f"File does not exist: {dest}")
            return True, None, []

        old_slurp = self._slurp(dest, task_vars=task_vars)
        old_content = old_slurp['content']
        old_lines = old_slurp['content_lines']
        self._display.vvv(f"Old lines: {old_lines}")

        if lines != old_lines:
            self._display.vvv("Content changed (lines comparison)")
            changed = True

        old_perms = self._get_perms(dest, selinux=selinux, task_vars=task_vars)
        self._display.vvv(f"Old perms: {old_perms}")

        if perms:
            for key in [
                'owner', 'group', 'selevel', 'serole', 'setype', 'seuser'
            ]:
                if perms.get(key) and perms[key] != old_perms.get(key):
                    self._display.vvv(
                        f"Perm {key} changed: {perms[key]} != {old_perms.get(key)}"
                    )
                    changed = True

            if perms.get('mode'):
                try:
                    symbol_perms = self._convert_octal_mode_to_symbolic(
                        perms['mode']
                    )
                    if symbol_perms != old_perms['mode']:
                        self._display.vvv(
                            f"Mode changed: {symbol_perms} != {old_perms['mode']}"
                        )
                        changed = True
                except Exception as e:
                    raise AnsibleError(
                        f"Invalid mode: {perms['mode']}: {e}"
                    )

        self._display.vvv(f"Comparison result: changed is {changed}")

        return changed, old_content, old_lines

    def _apply_perms_and_selinux(
            self, dest, perms, selinux=False, task_vars=None
    ):
        """
        Apply ownership, permission mode, and SELinux context to a remote file.

        This method sets the owner, group, and file mode on the destination
        path if specified in `perms`. It also applies the SELinux context if
        `selinux` is True. Then verifies the applied values match expectations.

        :param dest: Remote file path to update
        :param perms: Dictionary with keys 'owner', 'group', 'mode', etc.
        :param selinux: Boolean indicating whether SELinux handling is enabled
        :param task_vars: Ansible task variables
        :raises: AnsibleError on failure to apply or verify any permission or
                 SELinux step
        """
        self._display.vvv(f"Applying permissions to {dest}")
        cmd = self._cmd

        if perms:
            if perms.get("owner"):
                chown_result = cmd(
                    ["chown", perms["owner"], dest], task_vars=task_vars
                )
                if chown_result["rc"] != 0:
                    raise AnsibleError(
                        f"Failed to chown {dest}: "
                        f"{chown_result.get('stderr', '')}"
                    )

            if perms.get("group"):
                chgrp_result = cmd(
                    ["chgrp", perms["group"], dest], task_vars=task_vars
                )
                if chgrp_result["rc"] != 0:
                    raise AnsibleError(
                        f"Failed to chgrp {dest}: "
                        f"{chgrp_result.get('stderr', '')}"
                    )

            if perms.get("mode"):
                chmod_result = cmd(
                    ["chmod", perms["mode"], dest], task_vars=task_vars
                )
                if chmod_result["rc"] != 0:
                    raise AnsibleError(
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
                "owner", "group", "selevel", "serole", "setype", "seuser"
            ]:
                if perms.get(key) and final_perms.get(key) != perms.get(key):
                    raise AnsibleError(
                        f"Post-apply verification failed: expected {key}="
                        f"{perms[key]}, got {final_perms.get(key)}"
                    )

            if perms.get("mode"):
                try:
                    expected_mode = self._convert_octal_mode_to_symbolic(
                        perms['mode']
                    )
                    actual_mode = final_perms.get("mode")
                    if actual_mode != expected_mode:
                        raise AnsibleError(
                            'Post-apply verification failed: expected mode='
                            f"{expected_mode}, got {actual_mode}"
                        )
                except Exception as e:
                    raise AnsibleError(
                        f"Invalid mode format: {perms['mode']}: {e}"
                    )

    def _make_raw_tmp_path(self, task_vars=None):
        """
        Create a temporary directory on the remote host using raw shell fallback.

        Returns:
            str: The path to the created temporary directory.
        Raises:
            AnsibleError: If directory creation fails.
        """
        cmd = self._cmd
        shell = self._connection._shell
        task_vars = task_vars or {}

        if not shell.tmpdir:
            # Try to create a tmp dir like Ansible's default: /tmp/ansible_xyz
            self._display.vvv("Creating temporary directory")
            tmp_path_cmd = ['mktemp', '-d', '/tmp/ansible.XXXXXX']
            cmd_results = cmd(tmp_path_cmd, task_vars=task_vars)

            if cmd_results['rc'] != 0 or not cmd_results['stdout']:
                raise AnsibleError(
                    "Failed to create temporary directory via raw fallback: "
                    f"{cmd_results['stderr']}"
                )

            tmpdir = cmd_results['stdout_lines'][0]
            shell.tmpdir = tmpdir  # Simulate Ansible's behavior

    def _write_file(
        self,
        content,
        dest,
        perms=None,
        backup=False,
        validate_cmd=None,
        check_mode=None,
        task_vars=None,
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
        self._display.vvv(f"Starting _write_file to {dest}")

        cmd = self._cmd
        shell = self._connection._shell
        backup_path = None
        check_mode = check_mode or False
        results = {'changed': False}

        self._make_raw_tmp_path(task_vars=task_vars)
        tmpdir = shell.tmpdir
        self._display.vvv(f"Using temporary directory: {tmpdir}")
        tmpfile = shell.join_path(tmpdir, "ansible_tmpfile")
        self._display.vvv(f"Using temporary file: {tmpfile}")

        old_stat = self._pseudo_stat(dest, task_vars=task_vars)
        self._display.vvv(f"Old stat: {old_stat}")
        if old_stat['exists'] and old_stat['type'] != 'file':
            raise AnsibleError(f"Cannot write over {old_stat['type']}")

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
        results['changed'] = changed

        # Calculate diff
        if task_vars.get('diff', False) and results['changed']:
            diff = '\n'.join(difflib.unified_diff(
                old_lines,
                lines,
                fromfile=dest,
                tofile=dest,
                lineterm=''
            ))
            results['diff'] = {
                'before_header': dest,
                'after_header': dest,
                'before': old_content,
                'after': content,
                'unified_diff': diff
            }
            self._display.vvv(f"Generated diff: {diff}")

        if check_mode:
            self._display.vvv("Check mode is enabled")
            if results['changed']:
                results.update({
                    'msg': 'Check mode: changes would have been made.'
                })
            else:
                results.update({
                    'msg': 'Check mode: no changes needed.'
                })

        else:
            if results['changed']:
                # Move the temp file to the final destination
                mv_result = cmd(["mv", tmpfile, dest], task_vars=task_vars)
                self._display.vvv(f"mv result: {mv_result}")
                if mv_result["rc"] != 0:
                    raise AnsibleError(
                        'Failed to move temp file into place: '
                        f"{mv_result.get('stderr', '')}"
                    )

                # Apply final permissions and ownership
                self._apply_perms_and_selinux(
                    dest, perms, selinux, task_vars=task_vars
                )

                results['msg'] = 'File written successfully'
            else:
                self._display.vvv('Files identical, no change necessary')
                results['msg']: "File not changed"

        results['rc'] = 0

        if backup_path:
            results["backup_file"] = backup_path

        self._display.vvv(f"_write_file completed: {results}")
        return results

    def _mk_dest_dir(self, file_path, task_vars=None):
        """
        Create the parent directory of the target file if it does not exist.

        Returns:
            dict: {
                'changed' (bool): True if directory would be or was created,
                'failed' (bool): True if directory creation failed
                                 (only in non-check mode),
                'msg' (str): Error message if applicable
            }
        """
        self._display.vvv(f"Starting _mk_dest_dir ({file_path})")
        dir_path = path.dirname(file_path)
        dir_stat = self._pseudo_stat(dir_path, task_vars=task_vars)
        if not dir_stat['exists']:
            if self._task.check_mode:
                self.results['changed'] = True
            else:
                try:
                    mkdir_results = self._mkdir(
                        dir_path, task_vars=task_vars
                    )
                    self.results['changed'] = True
                except Exception as e:
                    self.results.update({
                        'rc': 256,
                        'msg': (
                            f"Error creating {dir_path} "
                            f"({to_text(e)})"
                        ),
                        'failed': True,
                    })
