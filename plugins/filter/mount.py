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
from ansible_collections.o0_o.posix.plugins.module_utils.mount_utils import (
    _parse_mount,
)

DOCUMENTATION = r"""
---
name: mount
short_description: Parse mount command output
version_added: "1.1.0"
description:
  - Parse output from the mount command into structured data using jc
  - Returns a list of mount entries matching fstab structure
  - Unidirectional filter (parse only, no generation)
options:
  _input:
    description:
      - Command output from 'mount' as string, list of lines, or
        command result dict
    type: raw
    required: true
requirements:
  - jc (Python library)
notes:
  - The jc library parses mount output into structured data
  - Returns same structure as fstab filter (but without dump/pass)
  - Options are parsed into list of dicts for consistency with fstab
  - Type is always a string (never a list)
author:
  - oØ.o (@o0-o)
"""

EXAMPLES = r"""
# Parse mount output
- name: Get mount information
  ansible.builtin.command:
    cmd: mount
  register: mount_result

- name: Parse mount output and store
  ansible.builtin.set_fact:
    mount_info: "{{ mount_result.stdout | o0_o.posix.mount }}"

- name: Display root filesystem info
  vars:
    root_fs: >-
      {{ mount_info | selectattr('mount', 'equalto', '/') | first }}
  ansible.builtin.debug:
    msg: "Root mounted from {{ root_fs.source }} as {{ root_fs.type }}"
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
        - rw: true
        - relatime: true
        - errors: remount-ro
    - source: proc
      mount: /proc
      type: proc
      options:
        - rw: true
        - nosuid: true
        - nodev: true
        - noexec: true
    - source: server:/export
      mount: /mnt/nfs
      type: nfs
      options:
        - rw: true
        - vers: 4.0
"""


class FilterModule:
    """Filter for parsing mount command output."""

    def filters(self) -> dict[str, Any]:
        """Return the filter functions."""
        return {"mount": self.mount_filter}

    def mount_filter(
        self,
        config: Union[str, dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Parse mount output into structured data.

        Parses mount command output into normalized list of entries
        matching fstab structure (without dump/pass fields):
        - filesystem → source
        - mount_point → mount
        - type field or first option → type
        - remaining options → options (as list of dicts)

        :param config: Mount command output as string, list, or dict
        :returns: List of mount entries with standardized structure
        :raises AnsibleFilterError: If parsing fails
        """
        if isinstance(config, dict):
            config = config.get("stdout") or ""

        parsed, errors = _parse_mount(str(config), "")
        if parsed is not None:
            return parsed
        msg = to_native(errors[0]) if errors else "unknown error"
        raise AnsibleFilterError(f"mount failed: {msg}")
