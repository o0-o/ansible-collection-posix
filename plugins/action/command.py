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
import shlex
from typing import Any, Dict, Optional

from ansible import __version__ as ansible_version
from ansible.errors import AnsibleActionFail
from ansible.module_utils.common.collections import is_iterable
from ansible.module_utils.common.text.converters import to_native, to_text
from ansible_collections.o0_o.posix.plugins.action_utils import PosixBase

try:
    from packaging.version import parse as parse_version
except ImportError as imp_exc:
    PACKAGING_IMPORT_ERROR = imp_exc
else:
    PACKAGING_IMPORT_ERROR = None


class ActionModule(PosixBase):
    """Execute a command on the remote host with raw fallback support.

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

    def _raw_cmd(self, module_args: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Execute a command using low-level methods.

        Performs command execution using direct shell invocation when
        the standard Ansible command module is unavailable due to missing
        Python interpreter on the remote host.

        :param Optional[Dict[str, Any]] module_args: Module arguments
            dictionary containing command parameters
        :returns Dict[str, Any]: Command execution result dictionary
            containing stdout, stderr, return code, and timing information
        :raises AnsibleActionFail: When command execution fails or
            arguments are invalid

        .. note::
           This method handles shell vs non-shell execution modes,
           directory changes, and creates/removes conditional logic.
        """

        # Extract and normalize module arguments
        shell = module_args['_uses_shell']
        chdir = module_args['chdir']
        executable = module_args['executable']
        args = module_args['cmd']
        argv = module_args['argv']
        creates = module_args['creates']
        removes = module_args['removes']
        stdin = module_args['stdin']
        stdin_add_newline = module_args['stdin_add_newline']
        strip = module_args['strip_empty_ends']
        expand_vars = module_args['expand_argument_vars'] or None

        if stdin and stdin_add_newline:
            if not stdin.endswith('\n'):
                stdin = stdin + '\n'
        if isinstance(stdin, str):
            stdin = stdin.encode('utf-8')

        if expand_vars is not None and expand_vars != shell:
            raise AnsibleActionFail(
                'Raw fallback requires expand_argument_vars and _uses_shell '
                'to be the same. Shell-based execution expands variables '
                'remotely. If expand_argument_vars is true but _uses_shell is '
                'false, the fallback cannot expand variables.'
            )

        # Initialize return dict (mimics command module output)
        r = {
            'changed': False,
            'stdout': '',
            'stderr': '',
            'rc': None,
            'cmd': None,
            'start': None,
            'end': None,
            'delta': None,
            'msg': ''
        }

        # Warn if executable is set without shell=True
        if not shell and executable:
            self._display.warning(
                "As of Ansible 2.4, the parameter 'executable' is no "
                "longer supported with the 'command' module. Not using "
                f"'{executable}'."
            )
            executable = None

        # Tokenize raw params if using non-shell mode
        if not shell and args:
            args = shlex.split(args)

        args = args or argv

        # Ensure all args are safely converted to strings
        if is_iterable(args, include_strings=False):
            args = [
                to_native(
                    arg,
                    errors='surrogate_or_strict',
                    nonstring='simplerepr'
                )
                for arg in args
            ]

        r['cmd'] = args

        # If chdir is specified, validate the target directory
        if chdir:
            quoted_chdir = shlex.quote(chdir)
            cd_result = self._low_level_execute_command(
                f"cd {quoted_chdir}",
                executable=executable
            )
            if cd_result['rc'] != 0:
                raise AnsibleActionFail(
                    f"Unable to change directory before execution: {chdir}"
                )

        # Use creates/removes logic for check_mode idempotence
        shoulda = "Would" if self._task.check_mode else "Did"

        if creates and not r['msg']:
            quoted_creates = shlex.quote(creates)
            cr = self._low_level_execute_command(f"test -e {quoted_creates}")
            if cr['rc'] == 0:
                r['msg'] = f"{shoulda} not run command since '{creates}' exists"
                r['stdout'] = f"skipped, since {creates} exists"
                r['stdout_lines'] = [r['stdout']]
                r['stderr_lines'] = []
                r['rc'] = 0
                return r

        if removes and not r['msg']:
            quoted_removes = shlex.quote(removes)
            rm = self._low_level_execute_command(f"test -e {quoted_removes}")
            if rm['rc'] != 0:
                r['msg'] = (
                    f"{shoulda} not run command since '{removes}' "
                    "does not exist"
                )
                r['stdout'] = f"skipped, since {removes} does not exist"
                r['stdout_lines'] = [r['stdout']]
                r['stderr_lines'] = []
                r['rc'] = 0
                return r

        r['changed'] = True

        # Actually run the command unless in check_mode
        if not r['msg']:
            if not self._task.check_mode:
                r['start'] = datetime.datetime.now()

                # Determine the final command to execute
                if shell:
                    if is_iterable(args, include_strings=False):
                        cmd_str = " ".join(shlex.quote(a) for a in args)
                    else:
                        cmd_str = args
                    cmd = shlex.join(['sh', '-c', cmd_str])
                else:
                    cmd = shlex.join(args)
                # Execute the command
                exec_result = self._low_level_execute_command(
                    cmd,
                    in_data=stdin,
                    executable=executable,
                    chdir=chdir
                )
                r.update(exec_result)
                r['end'] = datetime.datetime.now()
            else:
                r['rc'] = 0
                r['msg'] = "Command would have run if not in check mode"
                if creates is None and removes is None:
                    r['skipped'] = True
                    r['changed'] = False

        # Convert timestamps and delta to text
        if r['start'] is not None and r['end'] is not None:
            r['delta'] = to_text(r['end'] - r['start'])
            r['end'] = to_text(r['end'])
            r['start'] = to_text(r['start'])

        # Strip trailing newlines from output if requested and define
        # module stdout/err and stdout/err lines lists.
        if r.get('stdout'):
            if strip:
                r['stdout'] = to_text(r['stdout']).rstrip("\r\n")
            r['module_stdout'] = r['stdout']
            r['stdout_lines'] = r['stdout'].splitlines()
        if r.get('stderr'):
            if strip:
                r['stderr'] = to_text(r['stderr']).rstrip("\r\n")
            r['module_stderr'] = r['stderr']
            r['stderr_lines'] = r['stderr'].splitlines()

        if r['rc'] != 0:
            r['msg'] = 'non-zero return code'

        return r

    def run(
        self, tmp: Optional[str] = None, task_vars: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Execute the command action with raw fallback capability.

        Main entry point that attempts command execution using the
        standard Ansible command module first, then falls back to raw
        shell execution if Python interpreter is missing on the remote
        host.

        :param Optional[str] tmp: Temporary directory path (unused in
            modern Ansible)
        :param Optional[Dict[str, Any]] task_vars: Task variables dictionary
        :returns Dict[str, Any]: Standard Ansible result dictionary

        :raises AnsibleActionFail: When the packaging module is missing,
            command arguments are invalid, or command execution fails

        .. note::
           This method validates arguments against a comprehensive
           specification and handles version compatibility for the
           expand_argument_vars parameter (Ansible 2.16+).
        """
        task_vars = task_vars or {}
        check_mode = self._task.check_mode

        if PACKAGING_IMPORT_ERROR:
            raise AnsibleActionFail(
                "The 'packaging' Python module is required to run this "
                f"plugin. Import failed: {PACKAGING_IMPORT_ERROR}"
            )

        # Define supported module arguments
        argument_spec = {
            '_uses_shell': {'type': 'bool', 'default': False},
            'cmd': {},
            'argv': {'type': 'list', 'elements': 'str'},
            'chdir': {'type': 'path'},
            'executable': {},
            'expand_argument_vars': {'type': 'bool'},
            'creates': {'type': 'path'},
            'removes': {'type': 'path'},
            'stdin': {'required': False},
            'stdin_add_newline': {'type': 'bool', 'default': True},
            'strip_empty_ends': {'type': 'bool', 'default': True},
            '_force_raw': {'type': 'bool', 'default': False},
        }

        validation_result, new_module_args = self.validate_argument_spec(
            argument_spec=argument_spec
        )
        self.force_raw = new_module_args.pop('_force_raw')
        if parse_version(ansible_version) < parse_version("2.16"):
            if new_module_args.get("expand_argument_vars") is not None:
                raise AnsibleActionFail(
                    "expand_argument_vars is not supported on Ansible "
                    "versions before 2.16"
                )

        input_keys = ('cmd', 'argv')
        provided = [
            k for k in input_keys if new_module_args.get(k) is not None
        ]

        if not provided:
            raise AnsibleActionFail(
                "One of 'cmd', or 'argv' must be specified"
            )

        if len(provided) > 1:
            raise AnsibleActionFail(
                "Only one of 'cmd', or 'argv' can be specified"
            )

        result = super().run(tmp, task_vars)
        result['invocation'] = self._task.args.copy()
        del tmp

        if not self.force_raw:
            builtin_module_args = new_module_args.copy()
            if builtin_module_args.get('expand_argument_vars') is None:
                builtin_module_args.pop('expand_argument_vars')
            builtin_module_args['_raw_params'] = builtin_module_args.pop('cmd')

            ansible_cmd_mod = self._execute_module(
                module_name='ansible.builtin.command',
                module_args=builtin_module_args,
                task_vars=task_vars,
            )
            ansible_cmd_mod.pop('invocation', None)

            if not self._is_interpreter_missing(ansible_cmd_mod):
                result.update(ansible_cmd_mod)
                result['raw'] = False
            else:
                self._display.warning(
                    "Ansible command module failed on host "
                    f"{task_vars.get('inventory_hostname', 'UNKOWN')}, "
                    "falling back to raw command."
                )
                self.force_raw = True

        if self.force_raw:
            cmd_result = self._raw_cmd(module_args=new_module_args)
            stderr = cmd_result.get('module_stderr', '').lower()
            result.update(cmd_result)
            result['raw'] = True

        self._remove_tmp_path(self._connection._shell.tmpdir)

        return result
