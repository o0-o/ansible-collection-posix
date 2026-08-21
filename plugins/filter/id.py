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

"""Filter wrapper for parsing id command output."""

from __future__ import annotations

from typing import Any

from ansible.errors import AnsibleFilterError
from ansible.module_utils.common.text.converters import to_native

from ansible_collections.o0_o.posix.plugins.module_utils import id_info

DOCUMENTATION = r"""
---
name: id
short_description: Parse id command output
version_added: "2.0.0"
description:
  - Parse output from the C(id) command using the jc parser and
    normalize it into user/group mappings that can be keyed by numeric
    ids or by names.
options:
  _input:
    description:
      - Output from the C(id) command either as text or as a registered
        result dictionary containing C(stdout).
    type: raw
    required: true
  key:
    description:
      - Select whether the resulting dictionaries are keyed by numeric
        ids or by names.
    type: str
    choices: [id, name]
    default: id
requirements:
  - jc
notes:
  - The jc library must be available on the controller.
  - The C(key) option chooses the keys of both mappings and switches
    every identity field between its numeric and its named form.
  - C(id) sends every identity through as a number, C(name) sends
    every identity through as a string, falling back to the
    stringified number for a group C(id) could not name.
  - C(users) describes the single user C(id) was asked about, so it
    holds at most one entry.
author:
  - oØ.o (@o0-o)
"""

EXAMPLES = r"""
- name: Ask the managed host who it is running as
  o0_o.posix.command:
    argv: ['id']
  register: id_result
  changed_when: false

- name: Parse id output keyed by numeric id
  ansible.builtin.set_fact:
    identity: "{{ id_result | o0_o.posix.id }}"

- name: Report the effective UID and its groups
  vars:
    uid: "{{ identity.users | list | first }}"
  ansible.builtin.debug:
    msg: >-
      UID {{ uid }} is {{ identity.users[uid].name }} in GIDs
      {{ identity.users[uid].groups | join(', ') }}

- name: Parse id output keyed by name instead
  ansible.builtin.set_fact:
    identity_by_name: "{{ id_result | o0_o.posix.id(key='name') }}"

- name: Fail unless the remote user is in the wheel group
  ansible.builtin.assert:
    that:
      - "'wheel' in identity_by_name.groups"
"""

RETURN = r"""
_value:
  description: >-
    The effective identity, split into the user C(id) reported and
    every group that user belongs to
  type: dict
  returned: always
  contains:
    users:
      description:
        - The single user C(id) reported, keyed by stringified UID, or
          by username when C(key) is C(name).
        - Empty when the output named no user, or when C(key) is
          C(name) and the UID could not be named.
      type: dict
      returned: always
      contains:
        name:
          description: >-
            Username, C(null) when the output gives only a number; the
            key already carries it in C(name) mode, where this field
            is absent
          returned: when C(key) is C(id)
          type: str
          sample: o0-o
        id:
          description: >-
            Numeric user ID; the key already carries it in C(id) mode,
            where this field is absent
          returned: when C(key) is C(name)
          type: int
          sample: 1000
        group:
          description: >-
            The primary group, as a GID under C(key=id) and as a name
            under C(key=name); C(null) when the output names no
            primary group
          type: raw
          sample: 20
        groups:
          description: >-
            Every group the user belongs to, primary group included,
            as GIDs under C(key=id) and as names under C(key=name),
            in the order C(id) printed them
          type: list
          elements: raw
          sample: [20, 101]
    groups:
      description:
        - Every group named in the output, keyed by stringified GID,
          or by group name when C(key) is C(name).
        - A group the output leaves unnamed is keyed by its stringified
          GID under either C(key).
      type: dict
      returned: always
      contains:
        name:
          description: >-
            Group name, C(null) when the output gives only a number;
            the key already carries it in C(name) mode, where this
            field is absent
          returned: when C(key) is C(id)
          type: str
          sample: staff
        id:
          description: >-
            Numeric group ID; the key already carries it in C(id)
            mode, where this field is absent
          returned: when C(key) is C(name)
          type: int
          sample: 20
  sample:
    users:
      "1000":
        name: o0-o
        group: 20
        groups: [20, 101]
    groups:
      "20":
        name: staff
      "101":
        name: access_bpf
"""


class FilterModule:
    """Expose the id normalization helper as a filter."""

    def filters(self) -> dict[str, Any]:
        return {"id": self.id_filter}

    def id_filter(self, config: Any, key: str = "id") -> dict[str, Any]:
        try:
            return id_info(config, key=key)
        except (ValueError, ImportError) as exc:
            raise AnsibleFilterError(
                f"id failed: {type(exc).__name__}: {to_native(exc)}"
            ) from exc
