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

from typing import Any, Union

from ansible.errors import AnsibleFilterError
from ansible.module_utils.common.text.converters import to_native
from ansible_collections.o0_o.posix.plugins.module_utils import hosts

DOCUMENTATION = r"""
---
name: hosts
short_description: Parse or generate /etc/hosts content
version_added: "1.4.0"
description:
  - Bidirectional filter for /etc/hosts content
  - Parse hosts file text into structured data using jc
  - Generate hosts file text from structured entries
  - Automatically detects operation based on input type
options:
  _input:
    description: |
      For parsing: hosts file content as string, list of lines, or
      command output dict. For generation: list of host entry dicts
      with address and hostnames list.
    type: raw
    required: true
requirements:
  - jc (Python library)
notes:
  - Automatically detects whether to parse or generate based on input
  - For parsing, returns normalized list of host entries
  - For generation, returns formatted hosts file text
  - Each entry has address and hostnames list (primary + aliases)
  - Comments are not preserved during parsing
author:
  - oØ.o (@o0-o)
"""

EXAMPLES = r"""
# Parse hosts file content
- name: Read and parse hosts file
  o0_o.posix.read:
    path: /etc/hosts
    content: true
  register: hosts_content

- name: Parse hosts into structured data
  ansible.builtin.set_fact:
    hosts_entries: >-
      {{ hosts_content['paths']['/etc/hosts']['content']
         | o0_o.posix.hosts }}

- name: Display localhost entry
  vars:
    localhost_entry: >-
      {{ hosts_entries
         | selectattr('address', 'equalto', '127.0.0.1')
         | first }}
  ansible.builtin.debug:
    msg: "Localhost hostnames: {{ localhost_entry.hostnames }}"

# Generate hosts file content
- name: Define host entries
  ansible.builtin.set_fact:
    new_hosts:
      - address: 127.0.0.1
        hostnames:
          - localhost
          - localhost.localdomain
      - address: ::1
        hostnames:
          - localhost
          - ip6-localhost
          - ip6-loopback
      - address: 192.168.1.10
        hostnames:
          - server1.example.com
          - server1

- name: Generate hosts content
  ansible.builtin.set_fact:
    new_hosts_file: "{{ new_hosts | o0_o.posix.hosts }}"

- name: Write new hosts file
  ansible.builtin.copy:
    content: "{{ new_hosts_file }}"
    dest: /etc/hosts.new
    backup: true
"""

RETURN = r"""
_value:
  description: List of host entries with standardized structure
  type: list
  elements: dict
  returned: always
  sample:
    - address: 127.0.0.1
      hostnames:
        - localhost
        - localhost.localdomain
    - address: ::1
      hostnames:
        - localhost
        - ip6-localhost
        - ip6-loopback
    - address: 192.168.1.10
      hostnames:
        - server1.example.com
        - server1
"""


class FilterModule:
    """Filter for parsing and generating hosts file content."""

    def filters(self) -> dict[str, Any]:
        """Return the filter functions."""
        return {"hosts": self.hosts_filter}

    def hosts_filter(
        self,
        config: Union[str, dict[str, Any], list[dict[str, Any]]],
    ) -> Union[list[dict[str, Any]], str]:
        """Parse or generate hosts file content.

        Bidirectional filter that either:
        1. Parses hosts file text into normalized list of entries
        2. Generates hosts file text from list of entries

        For parsing (string/list input):
        - ip → address
        - hostname → hostnames (list with primary + aliases)

        For generation (list of dicts input):
        - address → IP address
        - hostnames → list of hostnames (primary + aliases)

        :param config: Either hosts text to parse or list of entries
            to generate
        :returns: Either parsed entries list or generated hosts text
        :raises AnsibleFilterError: If parsing or generation fails
        """
        try:
            return hosts(config)
        except (ValueError, ImportError) as e:
            raise AnsibleFilterError(
                f"hosts failed: {type(e).__name__}: {to_native(e)}"
            ) from e
