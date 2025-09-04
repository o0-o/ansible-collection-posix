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

from ansible_collections.o0_o.posix.plugins.filter_utils import (
    FilesystemBase,
    JCBase,
)

DOCUMENTATION = r"""
---
name: mount
short_description: Parse mount command output
version_added: "1.1.0"
description:
  - Parse output from the mount command into structured data using jc
  - Can return either raw jc format or simplified facts structure
  - When used with facts=True, returns mount information organized by
    mount point
options:
  _input:
    description:
      - Command output from 'mount' as string, list of lines, or
        command result dict
    type: raw
    required: true
  facts:
    description:
      - If True, format output for direct merge into Ansible facts
      - Returns simplified structure with mounts organized by mount point
    type: bool
    default: false
requirements:
  - jc (Python library)
notes:
  - The jc library parses mount output into structured data
  - When facts=True, mount information is keyed by mount point for
    easy lookup
author:
  - oØ.o (@o0-o)
"""

EXAMPLES = r"""
# Parse mount output
- name: Get mount information
  ansible.builtin.command:
    cmd: mount
  register: mount_result

- name: Parse mount output
  ansible.builtin.debug:
    msg: "{{ mount_result.stdout | o0_o.posix.mount }}"

# Use facts format for simplified structure
- name: Parse for facts
  ansible.builtin.set_fact:
    mount_info: "{{ mount_result.stdout | o0_o.posix.mount(facts=true) }}"

- name: Display root filesystem info
  ansible.builtin.debug:
    msg: "Root mounted from {{ mount_info.mounts['/'].source }}"
"""

RETURN = r"""
# When facts=False (default)
_value:
  description: List of mount entries
  type: list
  elements: dict
  returned: always
  contains:
    filesystem:
      description: Source device or filesystem
      type: str
      sample: /dev/sda1
    mount_point:
      description: Directory where filesystem is mounted
      type: str
      sample: /home
    type:
      description: Filesystem type
      type: str
      sample: ext4
    options:
      description: Mount options
      type: list
      elements: str
      sample: ["rw", "relatime", "errors=remount-ro"]

# When facts=True
mounts:
  description: Mount information keyed by mount point
  type: dict
  returned: always
  contains:
    <mount_point>:
      description: Mount point information
      type: dict
      contains:
        source:
          description: Mount source when different from filesystem type
          type: str
          required: false
          sample: /dev/sda1
        type:
          description: Mount type classification
          type: str
          choices:
            - device
            - network
            - virtual
            - overlay
          sample: device
        filesystem:
          description: Filesystem type
          type: str
          sample: ext4
        pseudo:
          description: >-
            Whether this is a pseudo filesystem (kernel interface).
            Always present when type=virtual, true only for pseudo filesystems
          type: bool
          required: false
          sample: true
        fuse:
          description: Whether this is a FUSE filesystem
          type: bool
          sample: false
        options:
          description: Mount options as dictionary
          type: dict
          sample: {"rw": true, "relatime": true, "errors": "remount-ro"}
"""


class FilterModule(JCBase, FilesystemBase):
    """Filter for parsing mount command output using jc."""

    def filters(self) -> Dict[str, Any]:
        """Return the filter functions."""
        return {
            "mount": self.mount,
        }

    def _normalize_mount_data(
        self, parsed: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Normalize JC mount output to standardized format.

        Converts JC's mount parser output to the standard format expected
        by format_mounts_as_facts:
        - filesystem -> source
        - type -> filesystem (when present)
        - Extracts filesystem from first option on macOS/FreeBSD

        :param parsed: JC parsed mount data
        :returns: Normalized mount data
        """
        normalized = []

        for entry in parsed:
            mount_point = entry.get("mount_point")
            if not mount_point:
                continue

            # Start with normalized entry
            norm_entry = {
                "mount_point": mount_point,
                "options": list(entry.get("options", []).copy()),
            }

            # Get source (JC calls it 'filesystem')
            source = entry.get("filesystem")
            if source:
                norm_entry["source"] = source

            # Determine filesystem type
            filesystem = None
            if "type" in entry:
                # Linux style - explicit type field
                filesystem = entry["type"]
            elif norm_entry["options"]:
                # macOS/FreeBSD style - type is first option
                filesystem = norm_entry["options"].pop(0)

            if filesystem:
                norm_entry["filesystem"] = filesystem

            normalized.append(norm_entry)

        return normalized

    def mount(
        self,
        data: Union[str, List[str], Dict[str, Any]],
        facts: bool = False,
    ) -> Union[List[Dict[str, Any]], Dict[str, Any]]:
        """Parse mount output into structured data using jc.

        :param data: Command output from 'mount'
        :param facts: If True, format for direct merge into Ansible
            facts
        :returns: Parsed mount data, or facts structure with mounts by
            mount point
        """
        # Get parsed data from jc
        parsed = self.parse_command(data, "mount")

        if not facts:
            # Return jc's parsed format directly
            return parsed

        # Normalize and format for facts module
        normalized = self._normalize_mount_data(parsed)
        return self.format_mounts_as_facts(normalized)
