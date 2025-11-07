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
name: user
short_description: Look up user information by UID or username
version_added: "1.4.0"
description:
  - Look up user information from the C(users) fact by UID (int) or
    username (str).
  - The C(users) fact is typically set by the C(o0_o.posix.users)
    module.
  - When given an integer, looks up by UID. When given a string, looks
    up by username.
  - Returns C(None) if the user is not found.
options:
  _terms:
    description:
      - UID (int) or username (str) to look up.
    required: true
    type: list
    elements: raw
notes:
  - This lookup requires the C(users) fact to be available in the
    variable namespace.
  - The C(users) fact format matches the output from
    C(o0_o.posix.users) module.
  - If the C(users) fact is not available, the lookup will fail.
seealso:
  - module: o0_o.posix.users
    description: Gather POSIX user and group information
  - plugin: o0_o.posix.group
    plugin_type: lookup
    description: Look up group information by GID or name
"""

EXAMPLES = r"""
- name: Gather user information
  o0_o.posix.users:

- name: Look up user by UID
  ansible.builtin.debug:
    msg: "{{ lookup('o0_o.posix.user', 1000) }}"

- name: Look up user by username
  ansible.builtin.debug:
    msg: "{{ lookup('o0_o.posix.user', 'o0-o') }}"

- name: Get home directory for current user
  ansible.builtin.debug:
    msg: "{{ lookup('o0_o.posix.user', ansible_user_id)['home'] }}"

- name: Look up multiple users
  ansible.builtin.debug:
    msg: "{{ lookup('o0_o.posix.user', 0, 'root', 1000) }}"

- name: Handle user not found
  ansible.builtin.set_fact:
    user_data: "{{ lookup('o0_o.posix.user', 9999) }}"
  when: lookup('o0_o.posix.user', 9999) is not none

- name: Look up user from another host's facts
  ansible.builtin.debug:
    msg: "{{ lookup('o0_o.posix.user', 1000, host='webserver1') }}"

- name: Get user info from multiple hosts
  ansible.builtin.debug:
    msg: "Host {{ item }}: {{ lookup('o0_o.posix.user', 'deploy', host=item) }}"
  loop: "{{ groups['webservers'] }}"
  when: lookup('o0_o.posix.user', 'deploy', host=item) is not none

- name: Look up user with default value if not found
  ansible.builtin.set_fact:
    user_home: "{{ lookup('o0_o.posix.user', 'appuser', default={})['home'] | default('/opt/app') }}"

- name: Get user shell with fallback
  ansible.builtin.debug:
    msg: "Shell: {{ lookup('o0_o.posix.user', ansible_user_id, default={'shell': '/bin/sh'})['shell'] }}"

- name: Look up from another host with default
  ansible.builtin.set_fact:
    remote_user: "{{ lookup('o0_o.posix.user', 1000, host='remote_host', default=None) }}"
"""

RETURN = r"""
_raw:
  description:
    - User information dictionary, or C(None) if not found.
    - If multiple lookups were performed, returns a list.
  type: raw
  sample:
    name: o0-o
    gecos: 'User Account'
    home: /home/o0-o
    shell: /bin/bash
    group: 20
    groups:
      - 20
      - 101
"""

from ansible.errors import AnsibleLookupError
from ansible.plugins.lookup import LookupBase

from ansible_collections.o0_o.utils.plugins.module_utils import (
    VarsLookupBase,
)
from ansible_collections.o0_o.posix.plugins.module_utils.user_utils import (
    lookup_user,
)


class LookupModule(LookupBase, VarsLookupBase):
    """Look up user information by UID or username."""

    def run(self, terms, variables=None, **kwargs):
        """Perform the lookup.

        :param list terms: List of UIDs or usernames to look up
        :param dict variables: Available Ansible variables
        :returns list: List of user dictionaries or None values
        """
        # Extract default parameter if provided
        has_default = "default" in kwargs
        default = kwargs.pop("default", None)

        # Get the users fact using the inherited method
        try:
            users = self.lookup_var("users", default={}, **kwargs)
        except AnsibleLookupError as e:
            raise AnsibleLookupError(
                f"Failed to access 'users' fact. "
                f"Ensure o0_o.posix.users module has been run. Error: {e}"
            ) from e

        if not isinstance(users, dict):
            raise AnsibleLookupError(
                f"'users' fact is not a dictionary, got {type(users).__name__}"
            )

        ret = []
        for term in terms:
            # Template the term to resolve any Jinja2 expressions
            term = self._templar.template(term)

            user_data = lookup_user(term, users)

            # Return default if user not found and default was provided
            if user_data is None and has_default:
                ret.append(default)
            else:
                ret.append(user_data)

        return ret
