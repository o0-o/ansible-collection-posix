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

DOCUMENTATION = r"""
---
module: users
short_description: Gather POSIX user and group information
version_added: "2.0.0"
description:
  - Collects user and group information from C(/etc/passwd) and
    C(/etc/group) on POSIX hosts.
  - Gathers SSH keys from user home directories including authorized
    keys and public key files.
  - Returns the canonical C(o0_users) and C(o0_groups) mappings, keyed
    by stringified UID and GID and cross-referenced by numeric ID.
    The C(o0_o.posix.facts) module publishes the same shape under the
    same names, along with C(o0_shell_files) and the C(o0_paths)
    entries for the homes users live in and the login shells file.
options:
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
  shells_path:
    description:
      - Path to the C(/etc/shells) file.
      - A host that does not have this file leaves the path out of
        C(o0_paths) rather than filing it as a file that names no
        login shells.
    type: str
    default: /etc/shells
author:
  - oØ.o (@o0-o)
notes:
  - This module is implemented as an action plugin and supports raw
    fallback.
  - Group membership is reported in numeric IDs on both sides - a
    user's C(groups) lists GIDs and a group's C(members) lists UIDs -
    and every user counts as a member of their primary group.
  - Whether a user's shell is a known login shell is not stored. The
    login shells C(/etc/shells) names are the C(config) of that path
    in C(o0_paths), and the C(o0_o.posix.shells) lookup surfaces them,
    so C(user.shell in lookup('o0_o.posix.shells').shells) answers the
    question wherever it is asked and leaves no copy to go stale. The
    lookup is worth going through rather than reading the store
    directly, because it tells a host that names no login shells from
    one nothing ever asked.
  - SSH keys are only gathered if the user's C(.ssh) directory is
    readable.
  - Both C(authorized_keys) and C(authorized_keys2) files are checked
    per SSH daemon defaults.
  - If one authorized_keys file is readable but the other is not, a
    warning is issued indicating incomplete key information.
seealso:
  - plugin: o0_o.posix.shells
    plugin_type: lookup
    description: The login shells a host names
  - ref: o0_o.posix.id filter <ansible_collections.o0_o.posix.id_filter>
    description: Parse id command output
  - ref: o0_o.posix.group filter <ansible_collections.o0_o.posix.group_filter>
    description: Parse /etc/group content
  - ref: >-
      o0_o.posix.passwd filter
      <ansible_collections.o0_o.posix.passwd_filter>
    description: Parse /etc/passwd content
  - ref: >-
      o0_o.posix.authorized_keys filter
      <ansible_collections.o0_o.posix.authorized_keys_filter>
    description: Parse SSH authorized_keys content
"""

EXAMPLES = r"""
- name: Gather user and group information
  o0_o.posix.users:
  register: system_users

- name: Expose the canonical facts for the user and group lookups
  ansible.builtin.set_fact:
    o0_users: "{{ system_users['o0_users'] }}"
    o0_groups: "{{ system_users['o0_groups'] }}"

- name: Display SSH keys for a specific user
  ansible.builtin.debug:
    msg: "{{ system_users['o0_users']['1000']['keys'] }}"
  when: "'keys' in system_users['o0_users']['1000']"

- name: Check authorized keys for all users
  ansible.builtin.debug:
    msg: >-
      User {{ item.value.name }} has
      {{ item.value.keys.authorized | length }} authorized keys
  loop: "{{ system_users['o0_users'] | dict2items }}"
  when: item.value.keys is defined and item.value.keys.authorized is defined

- name: Find keys that exist in authorized_keys2
  ansible.builtin.debug:
    msg: "Key {{ item.key[:20] }}... is in authorized_keys2"
  loop: >-
    {{ system_users['o0_users']['1000']['keys']['authorized'] | dict2items }}
  when:
    - system_users['o0_users']['1000']['keys'] is defined
    - item.value.authorized_keys2 is defined
    - item.value.authorized_keys2

- name: List the members of a group by GID
  ansible.builtin.debug:
    msg: "{{ system_users['o0_groups']['20']['members'] }}"
"""

RETURN = r"""
o0_users:
  description: Mapping of users keyed by stringified UID
  returned: always
  type: dict
  contains:
    name:
      description: Username
      type: str
      sample: o0-o
    uid:
      description: Numeric user ID
      type: int
      sample: 1000
    gid:
      description: Numeric ID of the user's primary group
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
    groups:
      description: >-
        GIDs of every group the user belongs to, primary group
        included
      type: list
      elements: int
      sample: [20, 101]
    keys:
      description: SSH key information for the user
      returned: when user's .ssh directory is readable
      type: dict
      contains:
        authorized:
          description: >-
            Authorized keys from C(~/.ssh/authorized_keys) and
            C(~/.ssh/authorized_keys2) files, keyed by SSH key data
          returned: when authorized_keys files are readable
          type: dict
          sample:
            'AAAAB3NzaC1yc2EAAAADAQABAAABAQ...':
              type: ssh-rsa
              comment: user@example.com
            'AAAAC3NzaC1lZDI1NTE5AAAAIFq...':
              type: ssh-ed25519
              authorized_keys2: true
        public:
          description: >-
            Public key files from C(~/.ssh/*.pub), keyed by SSH key
            data. Only the first line of each .pub file is used.
          returned: when .ssh directory is readable
          type: dict
          sample:
            'AAAAB3NzaC1yc2EAAAADAQABAAABAQ...':
              type: ssh-rsa
              comment: user@host
              file: id_rsa.pub
            'AAAAC3NzaC1lZDI1NTE5AAAAIFq...':
              type: ssh-ed25519
              comment: personal-key
              file: id_ed25519.pub
o0_groups:
  description: >-
    Mapping of groups keyed by stringified GID. Each entry includes the
    group name when available, the GID, and the UIDs of every member.
  returned: always
  type: dict
  sample:
    "20":
      name: staff
      gid: 20
      members:
        - 0
        - 1000
o0_shell_files:
  description: >-
    Mapping of the login shell paths users actually hold to their file
    metadata. Distinct from the login shells C(/etc/shells) names,
    which are the C(config) of that path in C(o0_paths) whether anyone
    holds them or not.
  returned: always
  type: dict
  sample:
    /bin/sh:
      type: file
      uid: 0
      gid: 0
      tags:
        - posix
        - shell
o0_paths:
  description:
    - What the module observed about the paths it read, keyed by the
      canonical absolute path. The store is flat - a path is a key of
      its own and nothing about a path is filed under another path.
    - The homes users live in are entries here, tagged C(home) and
      carrying C(residents), the UIDs that call the path home. Two
      users sharing a home share one entry, and where a home is a
      symlink the target gets an entry of its own carrying the same
      residents, because that is where their files are.
    - A home the module read and found is not there is C(null), a
      dangling home. A home no read reached is left out entirely,
      because a store reports what it asked rather than what it
      assumed.
    - A single file parsed on its own lands at its own path - the
      bytes under C(content), the meaning parsed out of them under
      C(config) - so the login shells the host names are
      C(o0_paths[shells_path]['config']), surfaced by the
      C(o0_o.posix.shells) lookup. A host whose shells file could not
      be read leaves that path out rather than filing it as a file
      that names none, which is why the lookup answers unknown there
      rather than empty.
  returned: when the module observed a path
  type: dict
  contains:
    tags:
      description: >-
        What the path is to the collection - C(home) for a directory
        a user lives in
      type: list
      elements: str
    residents:
      description: >-
        For a home, the UIDs that call the path home
      type: list
      elements: int
    content:
      description: The bytes read from the path
      type: str
    config:
      description: >-
        The meaning parsed out of the file - for C(/etc/shells), the
        login shells it names, in the order it names them
      type: raw
  sample:
    /home/o0-o:
      type: directory
      uid: 1000
      gid: 20
      tags:
        - posix
        - home
      residents:
        - 1000
    /etc/shells:
      content: "/bin/sh\n/bin/zsh\n"
      config:
        - /bin/sh
        - /bin/zsh
"""
from ansible.module_utils.basic import AnsibleModule


def main() -> None:
    """Fail if this module is run directly without the action plugin."""

    argument_spec = {
        "passwd_path": {
            "type": "str",
            "default": "/etc/passwd",
            "no_log": False,
        },
        "group_path": {"type": "str", "default": "/etc/group"},
        "shells_path": {"type": "str", "default": "/etc/shells"},
    }

    module = AnsibleModule(
        argument_spec=argument_spec, supports_check_mode=True
    )
    module.fail_json(msg="This module must be run via its action plugin.")


if __name__ == "__main__":
    main()
