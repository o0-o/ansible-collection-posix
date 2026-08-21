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

"""Filter wrapper for parsing /etc/group content."""

from __future__ import annotations

from typing import Any

from ansible.errors import AnsibleFilterError
from ansible.module_utils.common.text.converters import to_native

from ansible_collections.o0_o.posix.plugins.module_utils import group_info

DOCUMENTATION = r"""
---
name: group
short_description: Parse /etc/group content
version_added: "2.0.0"
description:
  - Parse the contents of the C(/etc/group) file using the jc parser
    and normalize the output into a dictionary keyed by either numeric
    group ids or group names.
options:
  _input:
    description:
      - Raw C(/etc/group) content, the registered result from a
        command/slurp task, or pre-parsed entries.
    type: raw
    required: true
  key:
    description:
      - Choose whether the resulting mapping is keyed by numeric group
        ids or by names.
    type: str
    choices: [id, name]
    default: id
requirements:
  - jc
notes:
  - The jc library must be available on the controller.
  - The C(key) option chooses the mapping's key and renames the field
    that carries the GID, C(name) keying by group name with the GID in
    C(id), C(id) keying by stringified GID with the group name in
    C(name).
  - Members are the usernames C(/etc/group) lists, not their UIDs.
    They are the names on the fourth field of each line, so a user's
    primary group does not list them.
  - The password field is discarded.
author:
  - oØ.o (@o0-o)
"""

EXAMPLES = r"""
- name: Read /etc/group
  o0_o.posix.read:
    path: /etc/group
    content: true
  register: group_read

- name: Parse /etc/group keyed by GID
  ansible.builtin.set_fact:
    groups_by_gid: >-
      {{ group_read.paths['/etc/group'] | o0_o.posix.group }}

- name: Report the name of GID 0
  ansible.builtin.debug:
    msg: "GID 0 is {{ groups_by_gid['0'].name }}"

- name: Parse /etc/group keyed by name instead
  ansible.builtin.set_fact:
    groups_by_name: >-
      {{ group_read.paths['/etc/group']
         | o0_o.posix.group(key='name') }}

- name: Report which users are in the wheel group
  ansible.builtin.debug:
    msg: >-
      wheel is GID {{ groups_by_name.wheel.id }} with members
      {{ groups_by_name.wheel.members | join(', ') }}
  when: "'wheel' in groups_by_name"
"""

RETURN = r"""
_value:
  description:
    - Groups keyed by stringified GID, or by group name when C(key) is
      C(name).
    - In C(id) mode an entry whose GID is missing or non-numeric is
      dropped, since it has no key. In C(name) mode a nameless entry
      falls back to its stringified GID as the key.
  type: dict
  returned: always
  contains:
    name:
      description: >-
        Group name, C(null) when the line names none; the key already
        carries it in C(name) mode, where this field is absent
      returned: when C(key) is C(id)
      type: str
      sample: staff
    id:
      description: >-
        Numeric group ID, C(null) when the line's GID is missing or
        non-numeric; the key already carries it in C(id) mode, where
        this field is absent
      returned: when C(key) is C(name)
      type: int
      sample: 20
    members:
      description: >-
        Usernames listed as supplementary members of the group, empty
        when the line lists none
      type: list
      elements: str
      sample:
        - root
        - o0-o
  sample:
    "0":
      name: root
      members: []
    "20":
      name: staff
      members:
        - root
        - o0-o
"""


class FilterModule:
    """Expose the group normalization helper as a filter."""

    def filters(self) -> dict[str, Any]:
        return {"group": self.group_filter}

    def group_filter(
        self, config: Any, key: str = "id"
    ) -> dict[str, dict[str, Any]]:
        try:
            return group_info(config, key=key)
        except (ValueError, ImportError) as exc:
            raise AnsibleFilterError(
                f"group failed: {type(exc).__name__}: {to_native(exc)}"
            ) from exc
