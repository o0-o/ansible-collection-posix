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

from ansible.errors import AnsibleError
from ansible_collections.o0_o.posix.plugins.action_utils import PosixBase
from ansible import __version__ as ansible_version
from ansible.module_utils.common.text.converters import to_text, to_native
from ansible.module_utils.common.collections import is_iterable
import datetime
import shlex

try:
    from packaging.version import parse as parse_version
except ImportError as imp_exc:
    PACKAGING_IMPORT_ERROR = imp_exc
else:
    PACKAGING_IMPORT_ERROR = None


class ActionModule(PosixBase):
    """
    Execute a command on the remote host and fallback to raw execution
    if no Python interpreter is available.
    """

    TRANSFERS_FILES = False
    supports_check_mode = True

    def _raw_cmd(self, module_args=None):
        """Execute a command using low-level methods."""

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
            raise AnsibleError(
                "Raw fallback requires expand_argument_vars and _uses_shell "
                "to be the same. Shell-based execution expands variables "
                "remotely. If expand_argument_vars is true but _uses_shell is "
                "false, the fallback cannot expand variables."
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
                f"longer supported with the 'command' module. Not using "
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
                raise AnsibleError(
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

    def run(self, tmp=None, task_vars=None):
        """
        Execute the command action, with a fallback to raw if Python
        is not available on the remote host.
        """
        task_vars = task_vars or {}
        self._supports_async = False
        check_mode = self._task.check_mode

        if PACKAGING_IMPORT_ERROR:
            raise AnsibleError(
                "The 'packaging' Python module is required to run this plugin. "
                f"Import failed: {PACKAGING_IMPORT_ERROR}"
            )

        # Define supported module arguments
        argument_spec = dict(
            _uses_shell=dict(type='bool', default=False),
            cmd=dict(),
            argv=dict(type='list', elements='str'),
            chdir=dict(type='path'),
            executable=dict(),
            # Unlike builtin, expand is linked to shell
            expand_argument_vars=dict(type='bool'),
            creates=dict(type='path'),
            removes=dict(type='path'),
            stdin=dict(required=False),
            stdin_add_newline=dict(type='bool', default=True),
            strip_empty_ends=dict(type='bool', default=True),
            _force_raw=dict(type='bool', default=False),
        )

        # Validate input and extract usable arguments
        validation_result, new_module_args = self.validate_argument_spec(
            argument_spec=argument_spec
        )
        self.force_raw = new_module_args.pop('_force_raw')
        if parse_version(ansible_version) < parse_version("2.16"):
            if new_module_args.get("expand_argument_vars") is not None:
                raise AnsibleError(
                    "expand_argument_vars is not supported on Ansible "
                    "versions before 2.16"
                )

        # Enforce that exactly one input style is used
        input_keys = ('cmd', 'argv')
        provided = [k for k in input_keys if new_module_args.get(k) is not None]

        if not provided:
            raise AnsibleError(
                "One of 'cmd', or 'argv' must be specified"
            )

        if len(provided) > 1:
            raise AnsibleError(
                "Only one of 'cmd', or 'argv' can be specified"
            )

        # Initialize results using base Action class
        results = super().run(tmp, task_vars)
        results['invocation'] = self._task.args.copy()
        del tmp

        if self.force_raw:
            cmd_results = self._raw_cmd(module_args=new_module_args)
            results.update(cmd_results)
            results['raw'] = True
        else:
            # Attempt to use the builtin command module
            builtin_module_args = new_module_args.copy()
            if builtin_module_args.get('expand_argument_vars') is None:
                builtin_module_args.pop('expand_argument_vars')
            builtin_module_args['_raw_params'] = builtin_module_args.pop('cmd')
            try:
                ansible_cmd_mod = self._execute_module(
                    module_name='ansible.builtin.command',
                    module_args=builtin_module_args,
                    task_vars=task_vars,
                )
                ansible_cmd_mod.pop('invocation', None)
            except Exception as e:
                self._display.warning(
                    f"Error calling ansible.builtin.command: {to_text(e)}"
                )
                ansible_cmd_mod = {
                    'failed': True,
                    'rc': 127,
                    'module_stderr': to_text(e)
                }
                self._display.vvv(f"Failed command result: {ansible_cmd_mod}")
                self._display.vvv(f"Failed command args: {builtin_module_args}")

            # Check for missing interpreter and fall back if needed
            if self._is_interpreter_missing(ansible_cmd_mod):
                self._display.warning(
                    "Ansible command module failed on host "
                    f"{task_vars.get('inventory_hostname', 'UNKOWN')}, "
                    "falling back to raw command."
                )
                cmd_results = self._raw_cmd(module_args=new_module_args)
                results.update(cmd_results)
                results['raw'] = True
            else:
                results.update(ansible_cmd_mod)
                results['raw'] = False

        # Clean up temp files
        self._remove_tmp_path(self._connection._shell.tmpdir)

        return results
