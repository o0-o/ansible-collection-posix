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
version_added: "1.5.0"
description:
  - Collects user and group information from C(/etc/passwd) and
    C(/etc/group) on POSIX hosts.
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
    type: path
    default: /etc/passwd
  group_path:
    description:
      - Path to the C(/etc/group) file.
    type: path
    default: /etc/group
author:
  - oØ.o (@o0-o)
notes:
  - This module is implemented as an action plugin and supports raw fallback.
seealso:
  - filter: o0_o.posix.id
    description: Parse id command output
  - filter: o0_o.posix.group
    description: Parse /etc/group content
  - filter: o0_o.posix.passwd
    description: Parse /etc/passwd content
"""

EXAMPLES = r"""
- name: Gather users keyed by uid
  o0_o.posix.users:
  register: system_users

- name: Gather users keyed by name
  o0_o.posix.users:
    key: name
  register: system_users_by_name
"""

RETURN = r"""
users:
  description: Mapping of users keyed according to the I(key) option
  returned: always
  type: dict
  sample:
    "1000":
      name: o0-o
      gid: 20
      gecos: 'User Account'
      home: /home/o0-o
      shell: /bin/bash
      group: 20
      groups: [20, 101]
groups:
  description: Mapping of groups keyed according to the I(key) option.
    Each entry includes the group name when available and the group members.
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
        "passwd_path": {"type": "str", "default": "/etc/passwd"},
        "group_path": {"type": "str", "default": "/etc/group"},
    }

    module = AnsibleModule(
        argument_spec=argument_spec, supports_check_mode=True
    )
    module.fail_json(msg="This module must be run via its action plugin.")


if __name__ == "__main__":
    main()
