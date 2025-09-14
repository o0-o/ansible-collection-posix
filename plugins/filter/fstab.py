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
from ansible_collections.o0_o.posix.plugins.module_utils import JCBase
from ansible_collections.o0_o.utils.plugins.module_utils import (
    string2items,
    wantlist,
)

DOCUMENTATION = r"""
---
name: fstab
short_description: Parse /etc/fstab file content
version_added: "1.5.0"
description:
  - Parse /etc/fstab file content into structured data using jc
  - Returns a list of mount entries with filesystem classification
    and structured options
  - Automatically classifies filesystem types and converts options to dictionary
  - Includes dump frequency and fsck pass information
options:
  _input:
    description:
      - Content of /etc/fstab as string, list of lines, or file content
    type: raw
    required: true
requirements:
  - jc (Python library)
notes:
  - The jc library parses fstab format into structured data
  - Returns a list structure matching other storage filters
  - Options are parsed into dictionary format for easier manipulation
  - Filesystem types are automatically classified (regular, virtual, network, overlay)
  - FUSE filesystems are automatically detected
  - Includes dump frequency and fsck pass information from fstab
author:
  - oØ.o (@o0-o)
"""

EXAMPLES = r"""
# Parse fstab content
- name: Read fstab file
  ansible.builtin.slurp:
    src: /etc/fstab
  register: fstab_content

- name: Parse fstab and store
  ansible.builtin.set_fact:
    fstab_info: "{{ fstab_content.content | b64decode | o0_o.posix.fstab }}"

- name: Display root filesystem info
  ansible.builtin.debug:
    msg: >-
      Root configured to mount from {{ (fstab_info | selectattr('mount', 'equalto', '/') | first).source }}
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
        defaults: true
        noatime: true
      dump:
        enabled: false
      fsck:
        enabled: true
        pass: 1
    - mount: /boot
      source: UUID=abc-123
      type: regular
      driver: ext2
      fuse: false
      options:
        defaults: true
        ro: true
      dump:
        enabled: true
        days: 1
      fsck:
        enabled: true
        pass: 2
    - mount: swap
      source: /dev/sda2
      type: paging
      options:
        sw: true
      dump:
        enabled: false
      fsck:
        enabled: false
"""


class FilterModule(JCBase):
    """Filter for parsing fstab file content using jc."""

    def filters(self) -> Dict[str, Any]:
        """Return the filter functions."""
        return {"fstab": self.fstab}

    def fstab(
        self, config: Union[str, List[str], Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Parse fstab file content with filesystem classification.

        Converts jc's fstab field names to standardized format:
        - fs_spec → source
        - fs_file → mount
        - fs_vfstype → type (single value preferred, list if multiple)
        - fs_mntops → options (as dictionary with key=value pairs)
        - fs_freq → dump
        - fs_passno → pass
        - Options are parsed as key=value or key=True for flags

        :param config: fstab config as string, list of lines, or dict
        :returns: List of mount entries with standardized structure
        """
        # Parse with jc
        parsed = self.parse_command(config, "fstab")

        # Normalize to standard format
        normalized = []
        for entry in parsed:
            norm_entry = {}

            norm_entry["source"] = entry.get("fs_spec")
            norm_entry["mount"] = entry.get("fs_file")

            # Parse vfstype with string2items first (in case of comma-separated types)
            # then use wantlist(false) to get single value if only one type
            try:
                types = string2items(entry.get("fs_vfstype"))
                norm_entry["type"] = wantlist(types, False)
            except (TypeError, ValueError) as e:
                raise AnsibleFilterError(f"Error parsing fs_vfstype: {e}") from e

            # Parse options string into list of dicts using string2items
            if "fs_mntops" in entry:
                # Use string2items to parse comma-separated options
                # It handles None/empty strings gracefully
                try:
                    options = string2items(entry["fs_mntops"])
                    norm_entry["options"] = []
                    for opt in options:
                        if "=" in opt:
                            # Split on first = only
                            key, value = opt.split("=", 1)
                            norm_entry["options"].append({key: value})
                        else:
                            # Treat as boolean flag
                            norm_entry["options"].append({opt: True})
                except (TypeError, ValueError) as e:
                    raise AnsibleFilterError(f"Error parsing fs_mntops: {e}") from e


            if "fs_freq" in entry:
                norm_entry["dump"] = int(entry["fs_freq"])
            else:
                norm_entry["dump"] = None

            if "fs_passno" in entry:
                norm_entry["pass"] = int(entry["fs_passno"])
            else:
                norm_entry["pass"] = None

            normalized.append(norm_entry)

        return normalized
