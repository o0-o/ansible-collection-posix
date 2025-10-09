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

"""Filter wrapper for parsing SSH authorized_keys content."""

from __future__ import annotations

from typing import Any, Dict, List

from ansible.errors import AnsibleFilterError
from ansible.module_utils.common.text.converters import to_native

from ansible_collections.o0_o.posix.plugins.module_utils import (
    authorized_keys,
)


DOCUMENTATION = r"""
---
name: authorized_keys
short_description: Parse SSH authorized_keys file content
version_added: "1.5.0"
description:
  - Parse the contents of an SSH C(authorized_keys) file into structured
    data.
  - Extracts key type, key data, optional comment, and optional
    restrictions/options.
  - Handles various input formats including raw content, command output,
    and slurp results.
options:
  _input:
    description:
      - Raw C(authorized_keys) content, the registered result from a
        command/slurp task, or pre-parsed entries.
      - Supports content as a string, command result with C(stdout), or
        slurp result with base64-encoded C(content).
    type: raw
    required: true
notes:
  - Blank lines and comment lines (starting with C(#)) are ignored.
  - Each entry may include optional restrictions/options before the key
    type.
  - "Common key types: C(ssh-rsa), C(ssh-ed25519), C(ecdsa-sha2-nistp256)"
  - Returns a list of dictionaries with C(type), C(key), optional
    C(comment), and optional C(options) keys.
seealso:
  - module: ansible.posix.authorized_key
    description: Manage SSH authorized_keys entries
author:
  - oØ.o (@o0-o)
"""

EXAMPLES = r"""
# Parse authorized_keys from slurp result
- name: Read authorized_keys file
  ansible.builtin.slurp:
    src: /home/user/.ssh/authorized_keys
  register: auth_keys_reg

- name: Parse the keys
  ansible.builtin.set_fact:
    parsed_keys: "{{ auth_keys_reg | o0_o.posix.authorized_keys }}"

# Parse from command output
- name: Get authorized_keys content
  ansible.builtin.command:
    cmd: cat /home/user/.ssh/authorized_keys
  register: keys_reg

- name: Parse keys from command output
  ansible.builtin.debug:
    msg: "{{ keys_reg | o0_o.posix.authorized_keys }}"

# Parse raw content
- name: Parse raw authorized_keys content
  ansible.builtin.set_fact:
    keys: >-
      {{ 'ssh-rsa AAAAB3NzaC1... user@example.com' |
         o0_o.posix.authorized_keys }}

# Example with options
- name: Parse key with restrictions
  ansible.builtin.debug:
    msg: >-
      {{ 'from="192.168.1.*" ssh-rsa AAAAB3... restricted' |
         o0_o.posix.authorized_keys }}
"""

RETURN = r"""
_value:
  description: List of parsed authorized key entries
  type: list
  elements: dict
  returned: always
  contains:
    type:
      description: SSH key algorithm type
      type: str
      sample: "ssh-ed25519"
    key:
      description: Base64-encoded public key data
      type: str
      sample: "AAAAC3NzaC1lZDI1NTE5AAAAIFq..."
    comment:
      description: Optional comment (usually email or description)
      type: str
      returned: when present
      sample: "user@example.com"
    options:
      description: List of SSH key options/restrictions
      type: list
      elements: dict
      returned: when options are present
      contains:
        name:
          description: Option name
          type: str
          sample: "from"
        value:
          description: Option value (None for flags)
          type: str
          returned: when option has a value
          sample: "192.168.1.*"
"""


class FilterModule:
    """Expose the authorized_keys parser as a filter."""

    def filters(self) -> Dict[str, Any]:
        return {"authorized_keys": self.authorized_keys_filter}

    def authorized_keys_filter(self, data: Any) -> List[Dict[str, Any]]:
        """Parse authorized_keys content into structured data.

        :param Any data: Input data (string, dict, or list)
        :returns List[Dict[str, Any]]: Parsed key entries
        :raises AnsibleFilterError: On parsing errors
        """
        try:
            return authorized_keys(data)
        except Exception as e:
            raise AnsibleFilterError(
                f"authorized_keys failed: {type(e).__name__}: "
                f"{to_native(e)}"
            ) from e
