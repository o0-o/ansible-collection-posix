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
name: fstab
short_description: Parse /etc/fstab file content
version_added: "1.5.0"
description:
  - Parse /etc/fstab file content into structured data using jc
  - Can return either raw jc format or normalized mount-compatible structure
  - When used with facts=True, returns mount information organized by
    mount point using the same structure as the mount filter
options:
  _input:
    description:
      - Content of /etc/fstab as string, list of lines, or file content
    type: raw
    required: true
  facts:
    description:
      - If True, normalize output to match mount filter structure
      - Returns structure compatible with o0_mounts facts
    type: bool
    default: false
requirements:
  - jc (Python library)
notes:
  - The jc library parses fstab format into structured data
  - When facts=True, output structure matches the mount filter for consistency
  - Options are parsed into dictionary format when facts=True
author:
  - oØ.o (@o0-o)
"""

EXAMPLES = r"""
# Parse fstab content
- name: Read fstab file
  ansible.builtin.slurp:
    src: /etc/fstab
  register: fstab_content

- name: Parse fstab
  ansible.builtin.debug:
    msg: "{{ fstab_content.content | b64decode | o0_o.posix.fstab }}"

# Use facts format for mount-compatible structure
- name: Parse for facts
  ansible.builtin.set_fact:
    fstab_info: "{{ fstab_content.content | b64decode | o0_o.posix.fstab(facts=true) }}"

- name: Display root filesystem info
  ansible.builtin.debug:
    msg: "Root configured to mount from {{ fstab_info.mounts['/'].source }}"
"""

RETURN = r"""
# When facts=False (default)
_value:
  description: List of fstab entries
  type: list
  elements: dict
  returned: always
  contains:
    fs_spec:
      description: Block special device or remote filesystem
      type: str
      sample: /dev/sda1
    fs_file:
      description: Mount point
      type: str
      sample: /home
    fs_vfstype:
      description: Filesystem type
      type: str
      sample: ext4
    fs_mntops:
      description: Mount options as comma-separated string
      type: str
      sample: defaults,noatime
    fs_freq:
      description: Dump frequency in days
      type: int
      sample: 0
    fs_passno:
      description: Pass number for fsck
      type: int
      sample: 2

# When facts=True
mounts:
  description: Mount information keyed by mount point (matches mount filter structure)
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
          sample: {"defaults": true, "noatime": true}
        dump:
          description: Dump frequency (fs_freq from fstab)
          type: int
          sample: 0
        pass:
          description: fsck pass number (fs_passno from fstab)
          type: int
          sample: 2
"""


class FilterModule(JCBase, FilesystemBase):
    """Filter for parsing fstab file content using jc."""

    def filters(self) -> Dict[str, Any]:
        """Return the filter functions."""
        return {
            "fstab": self.fstab,
        }

    def _normalize_to_mount_format(
        self, parsed: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Normalize fstab entries to match mount filter format.

        Converts jc's fstab field names to standardized format:
        - fs_spec → source
        - fs_file → mount_point
        - fs_vfstype → filesystem
        - fs_mntops → options (as list)
        - fs_freq → dump
        - fs_passno → pass

        :param parsed: Parsed fstab data from jc
        :returns: List with normalized field names
        """
        normalized = []
        for entry in parsed:
            normalized_entry = {
                "source": entry.get("fs_spec", ""),
                "mount_point": entry.get("fs_file", ""),
                "filesystem": entry.get("fs_vfstype", ""),
                "options": [],
            }

            # Parse options string into list
            options_str = entry.get("fs_mntops", "")
            if options_str:
                normalized_entry["options"] = [
                    opt.strip() for opt in options_str.split(",") if opt.strip()
                ]

            # Keep fstab-specific fields
            normalized_entry["dump"] = entry.get("fs_freq", 0)
            normalized_entry["pass"] = entry.get("fs_passno", 0)

            normalized.append(normalized_entry)

        return normalized

    def fstab(
        self, text: Union[str, List[str], Dict[str, Any]], facts: bool = False
    ) -> Union[List[Dict[str, Any]], Dict[str, Any]]:
        """Parse fstab file content using jc.

        :param text: fstab content as string, list of lines, or dict
        :param facts: If True, format for Ansible facts with mount-compatible structure
        :returns: Parsed fstab data (list or facts dict)
        """
        # Parse with jc
        parsed = self.parse_command(text, "fstab")

        if facts:
            # Normalize and format for facts module
            normalized = self._normalize_to_mount_format(parsed)
            return self.format_mounts_as_facts(normalized)

        return parsed
