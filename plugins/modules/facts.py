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

DOCUMENTATION = r'''
---
module: facts
short_description: Gather POSIX facts from the managed host
version_added: '1.1.0'
description:
  - Collects minimal OS and hardware facts from POSIX-compatible remote hosts.
  - Uses raw shell commands like C(uname) to gather kernel name, version,
    and CPU architecture.
  - Does not require Python on the managed host.
options:
  gather_subset:
    description:
      - List of fact subsets to gather.
      - Use C(all) to gather all available facts.
      - Use C(!subset) to exclude specific subsets.
    type: list
    elements: str
    default: [all]
    choices: [all, kernel, arch, '!all', '!kernel', '!arch']
author:
  - oØ.o (@o0-o)
seealso:
  - module: ansible.builtin.setup
notes:
  - This module must be run via its action plugin.
  - It is designed to support bootstrapping environments where Python
    may not be available on the managed node.
attributes:
  check_mode:
    description: This module supports check mode.
    support: full
  async:
    description: This module does not support async operation.
    support: none
  platform:
    description: Only POSIX platforms are supported.
    support: full
    platforms: posix
'''

EXAMPLES = r'''
- name: Gather all POSIX facts
  o0_o.posix.facts:

- name: Gather only kernel info
  o0_o.posix.facts:
    gather_subset:
      - kernel

- name: Gather architecture only
  o0_o.posix.facts:
    gather_subset:
      - arch

- name: Exclude kernel info
  o0_o.posix.facts:
    gather_subset:
      - '!kernel'
'''

RETURN = r'''
ansible_facts:
  description: Dictionary of gathered POSIX facts.
  returned: always
  type: dict
  contains:
    o0_os:
      description: Basic operating system facts.
      type: dict
      returned: when subset includes 'kernel'
      contains:
        kernel:
          description: Kernel metadata.
          type: dict
          contains:
            name:
              type: str
              description: Lowercase kernel name (e.g. "linux").
            pretty:
              type: str
              description: Original kernel name as returned by uname.
            version:
              description: Kernel version details.
              type: dict
              contains:
                id:
                  type: str
                  description: Kernel version string (e.g. "6.1.0").
        compliance:
          description: List of compliance identifiers.
          type: list
          elements: dict
          contains:
            name:
              type: str
              description: Internal compliance ID (e.g. "posix").
            pretty:
              type: str
              description: Human-readable compliance name (e.g. "POSIX").
    o0_hardware:
      description: Hardware architecture facts.
      type: dict
      returned: when subset includes 'arch'
      contains:
        cpu:
          description: CPU metadata.
          type: dict
          contains:
            architecture:
              type: str
              description: CPU architecture (e.g. "x86_64").
'''

from ansible.module_utils.basic import AnsibleModule


def main():
    """Fail if this module is run directly without the action plugin."""
    argument_spec = {
        'gather_subset': {
            'type': 'list',
            'elements': 'str',
            'default': ['all'],
            'choices': [
                'all', 'kernel', 'arch',
                '!all', '!kernel', '!arch'
            ]
        }
    }

    module = AnsibleModule(
        argument_spec=argument_spec,
        supports_check_mode=True
    )

    module.fail_json(msg='This module must be run via its action plugin.')


if __name__ == '__main__':
    main()
