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

from ansible_collections.o0_o.posix.plugins.filter_utils import JCBase

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
    msg: "Root mounted from {{ mount_info.mounts['/'].device }}"
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
        device:
          description: Source device path (only for /dev/ paths)
          type: str
          sample: /dev/sda1
        source:
          description: Network filesystem source (NFS, CIFS, etc.)
          type: str
          sample: nfs-server:/export/home
        filesystem:
          description: Type of filesystem
          type: str
          sample: ext4
        options:
          description: Mount options as list
          type: list
          elements: str
          sample: ["rw", "relatime"]
"""


class FilterModule(JCBase):
    """Filter for parsing mount command output using jc."""

    def filters(self) -> Dict[str, Any]:
        """Return the filter functions."""
        return {
            "mount": self.mount,
        }

    def _format_as_facts(self, parsed: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Format parsed mount data for Ansible facts structure.

        Converts jc's raw mount parsing into a simplified facts
        structure suitable for direct merge into Ansible facts, with
        mounts organized by mount point for easy lookup.

        :param parsed: Parsed mount data from jc
        :returns: Facts structure with mounts by mount point
        """
        mounts = {}

        for entry in parsed:
            mount_point = entry.get("mount_point")
            if not mount_point:
                continue

            # Create a clean copy without mount_point (it's the key)
            mount_info = {}

            # Handle source field (device for /dev paths, source for network)
            if "filesystem" in entry:
                source = entry["filesystem"]
                if source.startswith("/dev/"):
                    mount_info["device"] = source
                elif ":" in source or source.startswith("//"):
                    # Network filesystem (NFS, CIFS/SMB)
                    mount_info["source"] = source

            # Determine filesystem type
            if "type" in entry:
                # Use explicit type field if available
                mount_info["filesystem"] = entry["type"]
                # Use options as-is
                if "options" in entry:
                    mount_info["options"] = entry["options"]
            elif "options" in entry and entry["options"]:
                # On macOS, type is the first option
                options = entry[
                    "options"
                ].copy()  # Make a copy to avoid modifying original
                mount_info["filesystem"] = options.pop(0)
                # Store remaining options
                if options:
                    mount_info["options"] = options

            mounts[mount_point] = mount_info

        return {"mounts": mounts}

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

        # Format for facts module using separate method
        return self._format_as_facts(parsed)
