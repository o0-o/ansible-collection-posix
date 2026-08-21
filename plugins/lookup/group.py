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
name: group
short_description: Look up group information by GID or group name
version_added: "2.0.0"
description:
  - Look up group information from the C(o0_groups) fact by GID (int)
    or group name (str).
  - The C(o0_groups) fact is set by the C(o0_o.posix.facts) module and
    returned by the C(o0_o.posix.users) module.
  - An integer is the fact's own key. A string is matched against the
    C(name) field of each entry.
  - Returns C(None) if the group is not found.
options:
  _terms:
    description:
      - GID (int) or group name (str) to look up.
    required: true
    type: list
    elements: raw
notes:
  - This lookup requires the C(o0_groups) fact to be available in the
    variable namespace.
  - The fact is named C(o0_groups) rather than C(groups) because
    Ansible reserves C(groups) for the inventory group map.
  - If the C(o0_groups) fact is not available, the lookup will fail.
seealso:
  - module: o0_o.posix.users
    description: Gather POSIX user and group information
  - plugin: o0_o.posix.user
    plugin_type: lookup
    description: Look up user information by UID or username
"""

EXAMPLES = r"""
- name: Gather user and group information as facts
  o0_o.posix.facts:
    gather_subset: ['users']

- name: Look up group by GID
  ansible.builtin.debug:
    msg: "{{ lookup('o0_o.posix.group', 20) }}"

- name: Look up group by name
  ansible.builtin.debug:
    msg: "{{ lookup('o0_o.posix.group', 'staff') }}"

- name: Get members of a group
  ansible.builtin.debug:
    msg: "{{ lookup('o0_o.posix.group', 'staff')['members'] }}"

- name: Look up multiple groups
  ansible.builtin.debug:
    msg: "{{ lookup('o0_o.posix.group', 0, 'staff', 101) }}"

- name: Handle group not found
  ansible.builtin.set_fact:
    group_data: "{{ lookup('o0_o.posix.group', 9999) }}"
  when: lookup('o0_o.posix.group', 9999) is not none

- name: Look up group from another host's facts
  ansible.builtin.debug:
    msg: "{{ lookup('o0_o.posix.group', 'docker', host='appserver1') }}"

- name: Compare group membership across hosts
  ansible.builtin.debug:
    msg: >-
      {{ item }} docker members:
      {{ lookup('o0_o.posix.group', 'docker', host=item)['members'] }}
  loop: "{{ groups['docker_hosts'] }}"
  when: lookup('o0_o.posix.group', 'docker', host=item) is not none

- name: Look up group with default value if not found
  ansible.builtin.set_fact:
    group_members: >-
      {{
        lookup('o0_o.posix.group', 'developers', default={})['members']
        | default([])
      }}

- name: Get group with fallback to empty dict
  ansible.builtin.debug:
    msg: >-
      {{
        lookup('o0_o.posix.group', 9999,
               default={'name': 'unknown', 'members': []})
      }}

- name: Check if group exists across hosts with default
  ansible.builtin.set_fact:
    has_docker: >-
      {{
        lookup('o0_o.posix.group', 'docker', host=item, default=None)
        is not none
      }}
  loop: "{{ groups['all'] }}"
"""

RETURN = r"""
_raw:
  description:
    - Group information dictionary, or C(None) if not found.
    - If multiple lookups were performed, returns a list.
  type: raw
  sample:
    name: staff
    gid: 20
    members:
      - 0
      - 1000
"""

from ansible.errors import AnsibleLookupError
from ansible.plugins.lookup import LookupBase

from ansible_collections.o0_o.utils.plugins.module_utils import (
    VarsLookupBase,
)
from ansible_collections.o0_o.posix.plugins.module_utils import lookup_group


class LookupModule(LookupBase, VarsLookupBase):
    """Look up group information by GID or group name."""

    def run(self, terms, variables=None, **kwargs):
        """Perform the lookup.

        :param list terms: List of GIDs or group names to look up
        :param dict variables: Available Ansible variables
        :returns list: List of group dictionaries or None values
        """
        # Extract default parameter if provided
        has_default = "default" in kwargs
        default = kwargs.pop("default", None)

        # Get the o0_groups fact using the inherited method
        try:
            groups = self.lookup_var("o0_groups", default={}, **kwargs)
        except AnsibleLookupError as e:
            raise AnsibleLookupError(
                f"Failed to access 'o0_groups' fact. Ensure "
                f"o0_o.posix.facts or o0_o.posix.users has been run. "
                f"Error: {e}"
            ) from e

        if not isinstance(groups, dict):
            raise AnsibleLookupError(
                f"'o0_groups' fact is not a dictionary, "
                f"got {type(groups).__name__}"
            )

        ret = []
        for term in terms:
            # Template the term to resolve any Jinja2 expressions
            term = self._templar.template(term)

            group_data = lookup_group(term, groups)

            # Return default if group not found and default was provided
            if group_data is None and has_default:
                ret.append(default)
            else:
                ret.append(group_data)

        return ret
