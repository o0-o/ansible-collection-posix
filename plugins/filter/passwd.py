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

"""Filter wrapper for parsing /etc/passwd content."""

from __future__ import annotations

from typing import Any

from ansible.errors import AnsibleFilterError
from ansible.module_utils.common.text.converters import to_native

from ansible_collections.o0_o.posix.plugins.module_utils import passwd_info

DOCUMENTATION = r"""
---
name: passwd
short_description: Parse /etc/passwd content
version_added: "2.0.0"
description:
  - Parse the contents of the C(/etc/passwd) file using the jc parser
    and normalize the output into a dictionary keyed by either numeric
    user ids or user names.
options:
  _input:
    description:
      - Raw C(/etc/passwd) content, the registered result from a
        command/slurp task, or pre-parsed entries.
    type: raw
    required: true
  key:
    description:
      - Choose whether the resulting mapping is keyed by numeric user
        ids or by names.
    type: str
    choices: [id, name]
    default: id
requirements:
  - jc
notes:
  - The jc library must be available on the controller.
  - The C(key) option chooses the mapping's key and renames the field
    that carries the UID, C(name) keying by username with the UID in
    C(id), C(id) keying by stringified UID with the username in
    C(name). The primary group is C(gid) under either key.
  - The comment field is reported as C(gecos).
  - The password field is discarded.
author:
  - oØ.o (@o0-o)
"""

EXAMPLES = r"""
- name: Read /etc/passwd
  o0_o.posix.read:
    path: /etc/passwd
    content: true
  register: passwd_read

- name: Parse /etc/passwd keyed by UID
  ansible.builtin.set_fact:
    users_by_uid: >-
      {{ passwd_read.paths['/etc/passwd'] | o0_o.posix.passwd }}

- name: Report root's login shell
  ansible.builtin.debug:
    msg: "root logs in with {{ users_by_uid['0'].shell }}"

- name: Parse /etc/passwd keyed by name instead
  ansible.builtin.set_fact:
    users_by_name: >-
      {{ passwd_read.paths['/etc/passwd']
         | o0_o.posix.passwd(key='name') }}

- name: Report the deploy account's home directory
  ansible.builtin.debug:
    msg: >-
      deploy is UID {{ users_by_name.deploy.id }} at
      {{ users_by_name.deploy.home }}
  when: "'deploy' in users_by_name"
"""

RETURN = r"""
_value:
  description:
    - Users keyed by stringified UID, or by username when C(key) is
      C(name).
    - In C(id) mode an entry whose UID is missing or non-numeric is
      dropped, since it has no key. In C(name) mode a nameless entry
      falls back to its stringified UID as the key.
  type: dict
  returned: always
  contains:
    name:
      description: >-
        Username, C(null) when the line names none; the key already
        carries it in C(name) mode, where this field is absent
      returned: when C(key) is C(id)
      type: str
      sample: o0-o
    id:
      description: >-
        Numeric user ID, C(null) when the line's UID is missing or
        non-numeric; the key already carries it in C(id) mode, where
        this field is absent
      returned: when C(key) is C(name)
      type: int
      sample: 1000
    gid:
      description: >-
        Numeric ID of the user's primary group, C(null) when the
        line's GID is missing or non-numeric
      type: int
      sample: 20
    gecos:
      description: >-
        The comment field, C(null) when the line leaves it empty
      type: str
      sample: User Account
    home:
      description: >-
        Home directory path, C(null) when the line names none
      type: str
      sample: /home/o0-o
    shell:
      description: >-
        Login shell, C(null) when the line names none
      type: str
      sample: /bin/bash
  sample:
    "0":
      name: root
      gid: 0
      gecos: System Administrator
      home: /var/root
      shell: /bin/sh
    "1000":
      name: o0-o
      gid: 20
      gecos: User Account
      home: /home/o0-o
      shell: /bin/bash
"""


class FilterModule:
    """Expose the passwd normalization helper as a filter."""

    def filters(self) -> dict[str, Any]:
        return {"passwd": self.passwd_filter}

    def passwd_filter(
        self, config: Any, key: str = "id"
    ) -> dict[str, dict[str, Any]]:
        try:
            return passwd_info(config, key=key)
        except (ValueError, ImportError) as exc:
            raise AnsibleFilterError(
                f"passwd failed: {type(exc).__name__}: {to_native(exc)}"
            ) from exc
