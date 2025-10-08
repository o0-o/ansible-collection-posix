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

from typing import Any, Dict, List, Union

from ansible.errors import AnsibleFilterError
from ansible.module_utils.common.text.converters import to_native
from ansible_collections.o0_o.posix.plugins.module_utils import fstab

DOCUMENTATION = r"""
---
name: fstab
short_description: Parse or generate /etc/fstab content
version_added: "1.4.0"
description:
  - Bidirectional filter for /etc/fstab content
  - Parse fstab text into structured data using jc
  - Generate fstab text from structured mount entries
  - Automatically detects operation based on input type
options:
  _input:
    description: |
      For parsing: fstab content as string, list of lines, or
      command output dict. For generation: list of mount entry
      dicts with source, mount, type, options.
    type: raw
    required: true
requirements:
  - jc (Python library)
notes:
  - Automatically detects whether to parse or generate based on input
  - For parsing, returns normalized list of mount entries
  - For generation, returns formatted fstab text
  - Options are stored as list of dicts for flexible manipulation
  - Supports all standard fstab fields including dump and pass
  - Parses entries line-by-line with fallback for malformed entries
  - Handles OpenBSD-style entries without dump/pass fields (e.g., swap)
  - Setting dump and pass to None generates 4-field format (OpenBSD style)
  - Omitting dump and pass fields generates 6-field format with defaults
author:
  - oØ.o (@o0-o)
"""

EXAMPLES = r"""
# Parse fstab content
- name: Read and parse fstab file
  ansible.builtin.slurp:
    src: /etc/fstab
  register: fstab_content

- name: Parse fstab into structured data
  ansible.builtin.set_fact:
    fstab_entries: "{{ fstab_content.content | b64decode | o0_o.posix.fstab }}"

- name: Display root filesystem info
  vars:
    root_fs: >-
      {{ fstab_entries | selectattr('mount', 'equalto', '/') | first }}
  ansible.builtin.debug:
    msg: "Root configured to mount from {{ root_fs.source }}"

# Generate fstab content
- name: Define mount entries
  ansible.builtin.set_fact:
    new_mounts:
      - source: /dev/sda1
        mount: /
        type: ext4
        options:
          - defaults: true
          - noatime: true
        dump: 0
        pass: 1
      - source: /dev/sda2
        mount: /home
        type: ext4
        options:
          - defaults: true
        dump: 0
        pass: 2

- name: Generate fstab content
  ansible.builtin.set_fact:
    new_fstab: "{{ new_mounts | o0_o.posix.fstab }}"

- name: Write new fstab
  ansible.builtin.copy:
    content: "{{ new_fstab }}"
    dest: /etc/fstab.new
    backup: true

# Generate OpenBSD-style 4-field swap entry
- name: Define OpenBSD swap entry (omit dump/pass)
  ansible.builtin.set_fact:
    openbsd_swap:
      - source: e0cb35ae99f8f89d.b
        mount: null
        type: swap
        options:
          - sw: true
        dump: null
        pass: null

- name: Generate 4-field fstab line
  ansible.builtin.debug:
    msg: "{{ openbsd_swap | o0_o.posix.fstab }}"
  # Output: e0cb35ae99f8f89d.b  none  swap  sw
"""

RETURN = r"""
_value:
  description: List of mount entries with standardized structure
  type: list
  elements: dict
  returned: always
  sample:
    - source: /dev/sda1
      mount: /
      type: ext4
      options:
        - defaults: true
        - noatime: true
      dump: 0
      pass: 1
    - source: UUID=abc-123
      mount: /boot
      type: ext2
      options:
        - defaults: true
        - ro: true
      dump: 1
      pass: 2
    - source: /dev/sda2
      mount: none
      type: swap
      options:
        - sw: true
      dump: 0
      pass: 0
"""


class FilterModule:
    """Filter for parsing and generating fstab file content."""

    def filters(self) -> Dict[str, Any]:
        """Return the filter functions."""
        return {"fstab": self.fstab_filter}

    def fstab_filter(
        self,
        config: Union[str, Dict[str, Any], List[Dict[str, Any]]],
    ) -> Union[List[Dict[str, Any]], str]:
        """Parse or generate fstab content.

        Bidirectional filter that either:
        1. Parses fstab text into normalized list of mount entries
        2. Generates fstab text from list of mount entries

        For parsing (string/list input):
        - fs_spec → source
        - fs_file → mount
        - fs_vfstype → type
        - fs_mntops → options (as list of dicts)
        - fs_freq → dump
        - fs_passno → pass

        For generation (list of dicts input):
        - source → fs_spec
        - mount → fs_file
        - type → fs_vfstype
        - options → fs_mntops (comma-separated)
        - dump → fs_freq
        - pass → fs_passno

        :param config: Either fstab text to parse or list of entries
            to generate
        :returns: Either parsed entries list or generated fstab text
        :raises AnsibleFilterError: If parsing or generation fails
        """
        try:
            return fstab(config)
        except (ValueError, ImportError) as e:
            raise AnsibleFilterError(
                f"fstab failed: {type(e).__name__}: {to_native(e)}"
            ) from e
