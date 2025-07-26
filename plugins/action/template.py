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

from __future__ import absolute_import, division, print_function
__metaclass__ = type

import os
import shutil
import stat
import tempfile

from jinja2.defaults import (
    BLOCK_END_STRING,
    BLOCK_START_STRING,
    COMMENT_END_STRING,
    COMMENT_START_STRING,
    VARIABLE_END_STRING,
    VARIABLE_START_STRING,
)

from ansible import constants as C
from ansible.errors import AnsibleActionFail, AnsibleError
from ansible.module_utils.common.text.converters import (
    to_bytes, to_text
)
from ansible.module_utils.common.file import get_file_arg_spec
from ansible_collections.o0_o.posix.plugins.action_utils import PosixBase
from ansible.template import generate_ansible_template_vars


class ActionModule(PosixBase):

    TRANSFERS_FILES = True
    supports_check_mode = True
    supports_diff = True

    def _def_args(self):
        """
        Define and parse module arguments using the file argument spec,
        and store validated values as instance attributes.

        Returns:
            dict: The validated argument dictionary.
        """
        self._display.vvv("Defining argument spec")
        argument_spec = get_file_arg_spec()
        argument_spec.pop('attributes')
        argument_spec.update({
            'block_end_string': {
                'type': 'str',
                'default': BLOCK_END_STRING,
            },
            'block_start_string': {
                'type': 'str',
                'default': BLOCK_START_STRING,
            },
            'comment_end_string': {
                'type': 'str',
                'default': COMMENT_END_STRING,
            },
            'comment_start_string': {
                'type': 'str',
                'default': COMMENT_START_STRING,
            },
            'dest': {'type': 'path', 'required': True},
            'force': {'type': 'bool', 'default': True},
            'lstrip_blocks': {'type': 'bool', 'default': False},
            'newline_sequence': {
                'type': 'str',
                'choices': ['\n', '\r', '\r\n'],
                'default': '\n',
            },
            'src': {'type': 'path', 'required': True},
            'trim_blocks': {'type': 'bool', 'default': True},
            'backup': {'type': 'bool', 'default': False},
            'validate': {'type': 'str'},
            'variable_end_string': {
                'type': 'str',
                'default': VARIABLE_END_STRING,
            },
            'variable_start_string': {
                'type': 'str',
                'default': VARIABLE_START_STRING,
            },
            '_force_raw': {'type': 'bool', 'default': False},
        })

        validation_result, new_module_args = self.validate_argument_spec(
            argument_spec=argument_spec,
        )

        return new_module_args

    def run(self, tmp=None, task_vars=None):
        """
        Main entry point for the action plugin.

        Performs its own line presence/removal logic with raw fallback support,
        including reading, editing, and writing the file using POSIX-safe
        methods.

        Returns:
            dict: Standard Ansible result dictionary.
        """

        self._display.vvv("Starting template run()")
        task_vars = task_vars or {}
        self._supports_async = False

        new_module_args = self._def_args()

        self.results = super(ActionModule, self).run(tmp, task_vars=task_vars)
        self.results.update({
            'invocation': self._task.args.copy(),
            'changed': False,
            'raw': False,
            'msg': '',
        })

        del tmp

        # Required args
        src = new_module_args.get('src')
        dest = new_module_args.get('dest')
        if not src or not dest:
            raise AnsibleActionFail("src and dest are required")

        # Extract options
        newline_sequence = new_module_args.get('newline_sequence')
        trim_blocks = new_module_args.get('trim_blocks')
        lstrip_blocks = new_module_args.get('lstrip_blocks')

        variable_start_string = new_module_args.get('variable_start_string')
        variable_end_string = new_module_args.get('variable_end_string')
        block_start_string = new_module_args.get('block_start_string')
        block_end_string = new_module_args.get('block_end_string')
        comment_start_string = new_module_args.get('comment_start_string')
        comment_end_string = new_module_args.get('comment_end_string')
        force = new_module_args.get('force')

        self.force_raw = new_module_args.get('_force_raw')

        # Resolve src
        try:
            resolved_src = self._find_needle('templates', src)
        except AnsibleError as e:
            raise AnsibleActionFail(to_text(e))

        # Preserve mode if requested
        mode = new_module_args.get('mode')
        if mode == 'preserve':
            mode = '0%03o' % stat.S_IMODE(os.stat(resolved_src).st_mode)

        # Template content
        with open(resolved_src, encoding='utf-8') as f:
            template_data = f.read()

        searchpath = task_vars.get('ansible_search_path', [])
        searchpath.extend([self._loader._basedir, os.path.dirname(resolved_src)])
        searchpath = [
            os.path.join(p, 'templates') for p in searchpath
        ] + searchpath

        vars_copy = task_vars.copy()
        vars_copy.update(generate_ansible_template_vars(
            path=src,
            fullpath=resolved_src,
            dest_path=dest,
            # include_ansible_managed='ansible_managed' not in task_vars,
        ))

        overrides = {
            'block_start_string': block_start_string,
            'block_end_string': block_end_string,
            'variable_start_string': variable_start_string,
            'variable_end_string': variable_end_string,
            'comment_start_string': comment_start_string,
            'comment_end_string': comment_end_string,
            'trim_blocks': trim_blocks,
            'lstrip_blocks': lstrip_blocks,
            'newline_sequence': newline_sequence,
        }

        templar = self._templar.copy_with_new_env(
            searchpath=searchpath,
            available_variables=vars_copy
        )

        result_text = templar.template(
            template_data, escape_backslashes=False, overrides=overrides
        )
        result_text = result_text or ''

        # Create temp file
        local_tempdir = tempfile.mkdtemp(dir=C.DEFAULT_LOCAL_TMP)
        result_file = os.path.join(local_tempdir, os.path.basename(resolved_src))
        with open(to_bytes(result_file), 'wb') as f:
            f.write(to_bytes(result_text, encoding='utf-8'))

        try:
            if not self.force_raw:
                self._display.vvv('Attempt native execution to detect Python')
                new_task = self._task.copy()
                new_task.args['src'] = result_file
                new_task.args['dest'] = dest
                new_task.args['follow'] = True
                new_task.args['mode'] = mode

                for remove in (
                    'newline_sequence', 'block_start_string', 'block_end_string',
                    'variable_start_string', 'variable_end_string',
                    'comment_start_string', 'comment_end_string',
                    'trim_blocks', 'lstrip_blocks', '_force_raw',
                ):
                    new_task.args.pop(remove, None)

                copy_action = self._shared_loader_obj.action_loader.get(
                    'ansible.legacy.copy',
                    task=new_task,
                    connection=self._connection,
                    play_context=self._play_context,
                    loader=self._loader,
                    templar=self._templar,
                    shared_loader_obj=self._shared_loader_obj,
                )
                copy_result = copy_action.run(task_vars=task_vars)

                if not self._is_interpreter_missing(copy_result):
                    self._display.vvv("Delegated to ansible.builtin.copy")
                    copy_result.pop('invocation', None)
                    self.results['raw'] = False
                    self.results.update(copy_result)
                    return self.results
                else:
                    self._display.vvv(
                        "Python missing — falling back to raw mode"
                    )
                    self.force_raw = True

            if self.force_raw:
                try:
                    self._display.vvv(
                        "Creating parent directories (if needed)"
                    )
                    self._mk_dest_dir(dest, task_vars=task_vars)

                    self._display.vvv(f"Writing rendered template to {dest}")
                    perms = {key: new_module_args[key] for key in (
                        'owner', 'group', 'mode', 'selevel', 'serole',
                        'setype', 'seuser'
                    )}

                    if not force:
                        dest_stat = self._pseudo_stat(
                            dest, task_vars=task_vars
                        )

                    if force or not dest_stat['exists']:
                        write_result = self._write_file(
                            content=result_text,
                            dest=dest,
                            perms=perms,
                            backup=new_module_args.get('backup'),
                            validate_cmd=new_module_args.get('validate'),
                            check_mode=self._task.check_mode,
                            task_vars=task_vars,
                        )
                        self.results.update(write_result)

                    elif not force:
                        self.results['msg'] = (
                            "File exists and force is disabled, taking no "
                            "action"
                        )

                    else:
                        raise AnsibleActionFail("We should never get here")

                    self.results['raw'] = True

                except Exception as e:
                    self.results.update({
                        'failed': True,
                        'msg': f"Template rendering or writing failed: {e}"
                    })
        finally:
            # Clean up temporary files
            shutil.rmtree(to_bytes(
                local_tempdir, errors='surrogate_or_strict'
            ))
            self._remove_tmp_path(self._connection._shell.tmpdir)

        return self.results
