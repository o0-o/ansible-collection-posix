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
from ansible_collections.o0_o.posix.plugins.module_utils import (
    JCBase,
    StorageBase,
)

DOCUMENTATION = r"""
---
name: mount
short_description: Parse mount command output
version_added: "1.1.0"
description:
  - Parse output from the mount command into structured data using jc
  - Returns a list of mount entries with filesystem classification
    and structured options
  - Automatically classifies filesystem types and converts options to dictionary
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
  - Returns a list structure matching other storage filters
  - Options are parsed into dictionary format for easier manipulation
  - Filesystem types are automatically classified (regular, virtual, network, overlay)
  - FUSE filesystems are automatically detected
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
  ansible.builtin.debug:
    msg: >-
      Root mounted from {{ (mount_info | selectattr('mount', 'equalto', '/') | first).source }}
"""

RETURN = r"""
_value:
  description: List of mount entries with standardized structure
  type: list
  elements: dict
  returned: always
  sample:
    - mount: /
      source: /dev/sda1
      type: regular
      driver: ext4
      fuse: false
      options:
        rw: true
        relatime: true
        errors: remount-ro
    - mount: /proc
      source: kernel
      type: virtual
      driver: proc
      fuse: false
      options:
        rw: true
        nosuid: true
        nodev: true
        noexec: true
    - mount: /mnt/nfs
      source: server:/export
      type: network
      driver: nfs
      fuse: false
      options:
        rw: true
        vers: 4.0
"""


class FilterModule(JCBase, StorageBase):
    """Filter for parsing mount command output using jc."""

    def filters(self) -> Dict[str, Any]:
        """Return the filter functions."""
        return {
            "mount": self.mount,
        }


    def mount(
        self,
        data: Union[str, List[str], Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Parse mount output into structured data with filesystem classification.

        Converts JC's mount parser output to standardized format with:
        - mount_point -> mount
        - filesystem -> source
        - type -> driver (when present)
        - Extracts driver from first option on macOS/FreeBSD
        - Classifies filesystem types
        - Converts options to dictionary format

        :param data: Command output from 'mount'
        :returns: List of mount entries with standardized structure
        """
        # Get parsed data from jc
        parsed = self.parse_command(data, "mount")
        
        # Normalize to standard format
        normalized = []
        for entry in parsed:
            norm_entry = {"class": "filesystem"}

            if "mount_point" in entry:
                norm_entry["mount"] = entry["mount_point"]

            if "options" in entry:
                norm_entry["options"] = list(entry.get("options", []).copy())

            if "filesystem" in entry:
                norm_entry["source"] = entry["filesystem"]

            if "type" in entry:
                # Linux style - explicit type field
                norm_entry["driver"] = entry["type"]
            elif norm_entry.get("options"):
                # macOS/FreeBSD style - type is first option
                norm_entry["driver"] = norm_entry["options"].pop(0)

            normalized.append(norm_entry)

        # Format with filesystem classification
        try:
            return self.format_storage_as_facts(normalized)
        except Exception as e:
            raise AnsibleFilterError(str(e)) from e
