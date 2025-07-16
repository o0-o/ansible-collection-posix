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

from ansible.errors import AnsibleActionFail, AnsibleConnectionFailure
from ansible_collections.o0_o.posix.plugins.action_utils.posix_base import (
    PosixBase
)


class ActionModule(PosixBase):
    """Gather basic POSIX kernel and hardware facts"""

    TRANSFERS_FILES = False
    _requires_connection = False
    _supports_check_mode = True
    _supports_async = False

    def _get_kernel_and_hardware(self, task_vars=None):
        """
        Collect minimal OS facts from the remote POSIX system using `uname`.
        """
        un_s = self._cmd(
            ['uname', '-s'], task_vars=task_vars, check_mode=False
        )
        un_r = self._cmd(
            ['uname', '-r'], task_vars=task_vars, check_mode=False
        )
        un_m = self._cmd(
            ['uname', '-m'], task_vars=task_vars, check_mode=False
        )

        kernel_name = un_s['stdout_lines'][0]
        kernel_version = un_r['stdout_lines'][0]
        arch = un_m['stdout_lines'][0]

        self._display.vvv(f"Kernel name: {kernel_name}")
        self._display.vvv(f"Kernel version: {kernel_version}")
        self._display.vvv(f"Architecture: {arch}")

        kernel = {
            'pretty': kernel_name,
            'name': kernel_name.lower().replace(' ', '_'),
            'version': {
                'id': kernel_version,
            },
        }

        cpu = {
            'architecture': arch,
        }

        return kernel, cpu

    def run(self, tmp=None, task_vars=None):
        """
        Main entry point for the action plugin. Returns gathered facts
        under `o0_os` and `o0_hardware`.
        """
        task_vars = task_vars or {}
        tmp = None  # unused in modern Ansible

        argument_spec = dict(
            gather_subset=dict(
                type='list',
                elements='str',
                default=['all'],
                choices=[
                    'all', 'kernel', 'arch',
                    '!all', '!kernel', '!arch'
                ]
            )
        )

        validation_result, new_module_args = self.validate_argument_spec(
            argument_spec=argument_spec
        )
        gather_subset = new_module_args['gather_subset']

        result = super().run(tmp, task_vars)

        try:
            kernel, cpu = self._get_kernel_and_hardware(task_vars=task_vars)
        except AnsibleConnectionFailure:
            raise
        except Exception as e:
            self._display.vvv(
                "On error, assume the system isn't POSIX: "
                f"{type(e).__name__}: {e}"
            )
            result.update({
                'skipped': True,
                'skip_reason': "This does not appear to be a POSIX system.",
                'ansible_facts': {}
            })
            return result

        # Subset filtering
        all_subsets = {'kernel', 'arch'}
        if all(s.startswith('!') for s in gather_subset):
            selected_subsets = set(all_subsets)
        else:
            selected_subsets = set()

        for s in gather_subset:
            if s == 'all':
                selected_subsets = set(all_subsets)
            elif s == '!all':
                selected_subsets.clear()
            elif s.startswith('!'):
                selected_subsets.discard(s[1:])
            elif s in all_subsets:
                selected_subsets.add(s)
            else:
                raise AnsibleActionFail(f"Invalid gather_subset: {s}")

        # Pull in existing facts to extend
        ansible_facts = task_vars.get('ansible_facts', {})
        os_facts = ansible_facts.get('o0_os', {}).copy()
        hw_facts = ansible_facts.get('o0_hardware', {}).copy()
        facts = {}

        if 'kernel' in selected_subsets:
            os_facts['kernel'] = kernel

            compliance = os_facts.get('compliance', [])
            if not isinstance(compliance, list):
                compliance = []

            posix_entry = {'name': 'posix', 'pretty': 'POSIX'}
            if posix_entry not in compliance:
                compliance.append(posix_entry)

            os_facts['compliance'] = compliance

            facts['o0_os'] = os_facts

        if 'arch' in selected_subsets:
            hw_facts['cpu'] = hw_facts.get('cpu', {}).copy()
            hw_facts['cpu'].update(cpu)

            facts['o0_hardware'] = hw_facts

        result.update({'ansible_facts': facts})

        return result
