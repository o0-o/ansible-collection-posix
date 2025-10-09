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

__metaclass__ = type

DOCUMENTATION = r"""
---
module: users
short_description: Gather POSIX user and group information
version_added: "1.4.0"
description:
  - Collects user and group information from C(/etc/passwd) and
    C(/etc/group) on POSIX hosts.
  - Gathers SSH keys from user home directories including authorized
    keys and public key files.
  - Returns dictionaries keyed by either numeric ids or names that
    mirror the structure of the o0_o.posix.id filter output.
options:
  key:
    description:
      - Select how the resulting dictionaries are keyed.
      - When C(id) the mapping keys are stringified numeric identifiers.
      - When C(name) the mapping keys are user or group names.
    type: str
    choices: [id, name]
    default: id
  passwd_path:
    description:
      - Path to the C(/etc/passwd) file.
    type: str
    default: /etc/passwd
  group_path:
    description:
      - Path to the C(/etc/group) file.
    type: str
    default: /etc/group
author:
  - oØ.o (@o0-o)
notes:
  - This module is implemented as an action plugin and supports raw
    fallback.
  - SSH keys are only gathered if the user's C(.ssh) directory is
    readable.
  - Both C(authorized_keys) and C(authorized_keys2) files are checked
    per SSH daemon defaults.
  - If one authorized_keys file is readable but the other is not, a
    warning is issued indicating incomplete key information.
seealso:
  - ref: o0_o.posix.id filter <ansible_collections.o0_o.posix.id_filter>
    description: Parse id command output
  - ref: o0_o.posix.group filter <ansible_collections.o0_o.posix.group_filter>
    description: Parse /etc/group content
  - ref: o0_o.posix.passwd filter <ansible_collections.o0_o.posix.passwd_filter>
    description: Parse /etc/passwd content
  - ref: o0_o.posix.authorized_keys filter <ansible_collections.o0_o.posix.authorized_keys_filter>
    description: Parse SSH authorized_keys content
"""

EXAMPLES = r"""
- name: Gather users keyed by uid
  o0_o.posix.users:
  register: system_users

- name: Gather users keyed by name
  o0_o.posix.users:
    key: name
  register: system_users_by_name

- name: Display SSH keys for a specific user
  ansible.builtin.debug:
    msg: "{{ system_users['users']['1000']['keys'] }}"
  when: "'keys' in system_users['users']['1000']"

- name: Check authorized keys for all users
  ansible.builtin.debug:
    msg: "User {{ item.value.name }} has {{ item.value.keys.authorized | length }} authorized_keys files"
  loop: "{{ system_users['users'] | dict2items }}"
  when: item.value.keys is defined and item.value.keys.authorized is defined
"""

RETURN = r"""
users:
  description: Mapping of users keyed according to the I(key) option
  returned: always
  type: dict
  contains:
    name:
      description: Username
      type: str
      sample: o0-o
    gid:
      description: Primary group ID
      type: int
      sample: 20
    gecos:
      description: User comment/info field
      type: str
      sample: 'User Account'
    home:
      description: Home directory path
      type: str
      sample: /home/o0-o
    shell:
      description: Login shell
      type: str
      sample: /bin/bash
    group:
      description: Primary group (ID or name based on I(key))
      type: raw
      sample: 20
    groups:
      description: List of all groups (IDs or names based on I(key))
      type: list
      elements: raw
      sample: [20, 101]
    keys:
      description: SSH key information for the user
      returned: when user's .ssh directory is readable
      type: dict
      contains:
        authorized:
          description: >-
            Authorized keys from C(~/.ssh/authorized_keys) and
            C(~/.ssh/authorized_keys2) files
          returned: when authorized_keys files are readable
          type: dict
          sample:
            authorized_keys:
              - type: ssh-rsa
                key: AAAAB3NzaC1yc2EAAAADAQABAAABAQ...
                comment: user@example.com
            authorized_keys2:
              - type: ssh-ed25519
                key: AAAAC3NzaC1lZDI1NTE5AAAAIFq...
                comment: deploy-key
        public:
          description: Public key files from C(~/.ssh/*.pub)
          returned: when .ssh directory is readable
          type: dict
          sample:
            id_rsa.pub:
              - type: ssh-rsa
                key: AAAAB3NzaC1yc2EAAAADAQABAAABAQ...
                comment: user@host
            id_ed25519.pub:
              - type: ssh-ed25519
                key: AAAAC3NzaC1lZDI1NTE5AAAAIFq...
                comment: personal-key
groups:
  description: >-
    Mapping of groups keyed according to the I(key) option. Each entry
    includes the group name when available and the group members.
  returned: always
  type: dict
  sample:
    "20":
      name: staff
      members:
        - root
        - o0-o
"""
from ansible.module_utils.basic import AnsibleModule


def main() -> None:
    """Fail if this module is run directly without the action plugin."""

    argument_spec = {
        "key": {"type": "str", "choices": ["id", "name"], "default": "id"},
        "passwd_path": {
            "type": "str",
            "default": "/etc/passwd",
            "no_log": False,
        },
        "group_path": {"type": "str", "default": "/etc/group"},
    }

    module = AnsibleModule(
        argument_spec=argument_spec, supports_check_mode=True
    )
    module.fail_json(msg="This module must be run via its action plugin.")


if __name__ == "__main__":
    main()
