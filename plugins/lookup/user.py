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
version_added: "2.0.0"
description:
  - Look up user information from the C(o0_users) fact by UID (int) or
    username (str).
  - The C(o0_users) fact is set by the C(o0_o.posix.facts) module and
    returned by the C(o0_o.posix.users) module.
  - An integer is the fact's own key. A string is matched against the
    C(name) field of each entry.
  - Returns C(None) if the user is not found.
options:
  _terms:
    description:
      - UID (int) or username (str) to look up.
    required: true
    type: list
    elements: raw
  host:
    description:
      - Read C(o0_users) from another host's variables rather than the
        current host's.
      - A host that has not gathered the fact answers the same way a
        host with no such user does.
    type: str
  default:
    description:
      - Value to answer with in place of C(None) for a term that does
        not resolve.
      - Applies per term, so a lookup of several terms substitutes it
        only for the ones that did not resolve.
    type: raw
notes:
  - This lookup reads the C(o0_users) fact from the variable
    namespace.
  - A namespace holding no C(o0_users) fact is read as a namespace
    holding no users, so every term answers C(None) — or C(default)
    when one is given — rather than failing. Gather the fact first and
    check the answer; a missing fact and a missing user are not
    distinguishable here.
  - The lookup does fail when C(o0_users) is present but is not a
    dictionary.
seealso:
  - module: o0_o.posix.users
    description: Gather POSIX user and group information
  - plugin: o0_o.posix.group
    plugin_type: lookup
    description: Look up group information by GID or name
"""

EXAMPLES = r"""
- name: Gather user information as facts
  o0_o.posix.facts:
    gather_subset: ['users']

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
    msg: >-
      Host {{ item }}: {{ lookup('o0_o.posix.user', 'deploy', host=item) }}
  loop: "{{ groups['webservers'] }}"
  when: lookup('o0_o.posix.user', 'deploy', host=item) is not none

- name: Look up user with default value if not found
  ansible.builtin.set_fact:
    user_home: >-
      {{
        lookup('o0_o.posix.user', 'appuser', default={})['home']
        | default('/opt/app')
      }}

- name: Get user shell with fallback
  ansible.builtin.debug:
    msg: >-
      Shell: {{
        lookup('o0_o.posix.user', ansible_user_id,
               default={'shell': '/bin/sh'})['shell']
      }}

- name: Look up from another host with default
  ansible.builtin.set_fact:
    remote_user: >-
      {{
        lookup('o0_o.posix.user', 1000, host='remote_host', default=None)
      }}
"""

RETURN = r"""
_raw:
  description:
    - User information dictionary, or C(None) if not found.
    - If multiple lookups were performed, returns a list.
  type: raw
  sample:
    name: o0-o
    uid: 1000
    gid: 20
    gecos: 'User Account'
    home: /home/o0-o
    shell: /bin/bash
    groups:
      - 20
      - 101
"""

from ansible.errors import AnsibleLookupError
from ansible.plugins.lookup import LookupBase

from ansible_collections.o0_o.core.plugins.module_utils import (
    VarsLookupBase,
)
from ansible_collections.o0_o.posix.plugins.module_utils import lookup_user


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

        # Get the o0_users fact using the inherited method. The default
        # makes an absent fact an empty namespace rather than an error,
        # so every term answers not-found
        users = self.lookup_var("o0_users", default={}, **kwargs)

        if not isinstance(users, dict):
            raise AnsibleLookupError(
                f"'o0_users' fact is not a dictionary, got "
                f"{type(users).__name__}"
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
