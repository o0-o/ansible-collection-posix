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

from __future__ import annotations

from ansible.errors import AnsibleError
from ansible_collections.o0_o.posix.plugins.action_utils import PosixBase
from base64 import b64decode


class ActionModule(PosixBase):
    """
    Read the contents of a file from the remote host using the
    built-in slurp module, with fallback to raw 'cat' if the remote
    Python interpreter is unavailable.

    Returns UTF-8 decoded content in the 'content' key.
    """

    TRANSFERS_FILES = False

    def run(self, tmp=None, task_vars=None):
        """
        Read the base64 contents of a file from the remote host and
        fall back to raw 'cat' if no Python interpreter is available.
        """
        task_vars = task_vars or {}
        self._supports_async = False

        # Define the expected input parameters
        argument_spec = dict(
            src=dict(type='str', required=True),
            _force_raw=dict(type='bool', default=False),
        )

        # Validate input against spec and extract usable values
        validation_result, new_module_args = self.validate_argument_spec(
            argument_spec=argument_spec
        )
        src = new_module_args.get('src')
        force_raw = new_module_args.get('_force_raw')

        # Initialize the result structure from the base Action class
        results = super().run(tmp, task_vars)
        del tmp  # tmp is no longer needed

        if force_raw:
            cat_results = self._cat(src, task_vars=task_vars)
            results.update(cat_results)
            results['raw'] = True
        else:
            # Try using the builtin slurp module first
            try:
                ansible_slurp_mod = self._execute_module(
                    module_name='ansible.builtin.slurp',
                    module_args={'src': src},
                    task_vars=task_vars,
                )
                results['raw'] = False
            except Exception as e:
                # Handle failures due to module load or Python unavailability
                self._display.warning(
                    f"Error calling ansible.builtin.slurp: {str(e)}"
                )
                ansible_slurp_mod = {
                    'failed': True,
                    'rc': 127,
                    'module_stderr': str(e)
                }

            # Check if the module failed due to a missing Python interpreter
            if self._is_interpreter_missing(ansible_slurp_mod):
                self._display.warning(
                    "Ansible slurp module failed on host "
                    f"{task_vars.get('inventory_hostname', 'UNKNOWN')}, "
                    "falling back to raw 'cat'."
                )
                cat_results = self._cat(src, task_vars=task_vars)
                results.update(cat_results)
                results['raw'] = True
            elif 'content' in ansible_slurp_mod:
                # Try decoding base64 content from slurp result
                try:
                    ansible_slurp_mod.pop('encoding', None)
                    ansible_slurp_mod['content'] = b64decode(
                        ansible_slurp_mod['content']
                    ).decode('utf-8')
                except Exception as decode_error:
                    raise AnsibleError(
                        "Failed to base64 decode slurp content: "
                        f"{decode_error}"
                    )

                results.update(ansible_slurp_mod)

        # Slurp never changes
        results["changed"] = False

        # Clean up temporary files
        self._remove_tmp_path(self._connection._shell.tmpdir)

        return results
