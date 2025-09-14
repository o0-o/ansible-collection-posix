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

import re
from typing import Any, Dict, List, Union

from ansible.errors import AnsibleFilterError
from ansible_collections.o0_o.posix.plugins.module_utils import (
    JCBase,
    StorageBase,
)


DOCUMENTATION = r"""
---
name: df
short_description: Parse df command output
version_added: "1.4.0"
description:
  - Parse output from the df command into structured data using jc
  - Returns a list of mount entries with structured capacity information
    and filesystem classification
  - Automatically classifies filesystem types and formats capacity data
options:
  _input:
    description:
      - Command output from 'df' as string, list of lines, or
        command result dict
    type: raw
    required: true
requirements:
  - jc (Python library)
  - o0_o.utils collection (required for facts=True)
notes:
  - The jc library handles various df output formats (df, df -h, df -k, etc.)
  - Field names vary based on block size (1024_blocks, 512_blocks, size)
  - Returns a list structure matching other storage filters
  - Capacity values are provided in both bytes and human-readable format
  - Filesystem types are automatically classified (regular, virtual, network, overlay)
author:
  - oØ.o (@o0-o)
"""

EXAMPLES = r"""
# Parse df output
- name: Get filesystem usage
  ansible.builtin.command:
    cmd: df -h
  register: df_result

- name: Parse df output and store
  ansible.builtin.set_fact:
    fs_info: "{{ df_result.stdout | o0_o.posix.df }}"

- name: Display root filesystem usage
  ansible.builtin.debug:
    msg: >-
      Root uses {{ (fs_info | selectattr('mount', 'equalto', '/') | first).capacity.used.pretty }}
"""

RETURN = r"""
_output:
  description: List of mount entries with structured capacity data
  type: list
  elements: dict
  returned: always
  sample:
    - mount: /
      source: /dev/disk1s1
      type: regular
      driver: ext4
      fuse: false
      capacity:
        total:
          bytes: 499963174912
          pretty: "465.6 GiB"
        used:
          bytes: 313155427328
          pretty: "291.6 GiB"
    - mount: /System/Volumes/VM
      source: /dev/disk1s4
      type: regular
      driver: apfs
      fuse: false
      capacity:
        total:
          bytes: 499963174912
          pretty: "465.6 GiB"
        used:
          bytes: 5498036224
          pretty: "5.1 GiB"
"""


class FilterModule(JCBase, StorageBase):
    """Filter for parsing df command output using jc."""

    def filters(self) -> Dict[str, Any]:
        """Return the filter functions."""
        return {
            "df": self.df,
        }


    def df(
        self,
        data: Union[str, List[str], Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Parse df output into structured data with filesystem classification.

        Converts JC's df parser output to standardized format with:
        - mounted_on -> mount
        - filesystem -> source (when it's a device/path)
        - Extracts block_size from field names like 1024_blocks
        - Normalizes capacity data to total, used fields
        - Classifies filesystem types
        - Formats capacity with bytes and human-readable values

        :param data: Output from df command - string, list of lines, or
            command result
        :returns: List of mount entries with standardized structure
        """
        # Get parsed data from jc
        parsed = self.parse_command(data, "df")
        
        # Normalize to standard format
        normalized = []
        for entry in parsed:
            norm_entry = {"class": "filesystem"}

            if "mounted_on" in entry:
                norm_entry["mount"] = entry["mounted_on"]

            if "filesystem" in entry:
                norm_entry["source"] = entry["filesystem"]

            # Find block size from field names like 1024_blocks, 512_blocks
            for key in entry.keys():
                if key.endswith("_blocks"):
                    # Total is the value in this blocks field
                    norm_entry["total"] = entry[key]
                    # Extract the block size
                    block_size = key.replace("_blocks", "")
                    if block_size.isdigit():
                        norm_entry["block_size"] = f"{block_size}B"
                    elif re.match(r"^(\d+)([a-zA-Z]+)$", block_size):
                        # Handle formats like 1k_blocks, 1M_blocks
                        norm_entry["block_size"] = str(block_size)
                    del block_size
                    break

            # Handle size field (alternative to blocks)
            if "size" in entry and "total" not in norm_entry:
                # size field already has units
                norm_entry["total"] = entry["size"]

            # Handle used field
            if "used" in entry:
                norm_entry["used"] = entry["used"]

            normalized.append(norm_entry)

        # Format with filesystem classification and capacity formatting
        try:
            return self.format_storage_as_facts(normalized)
        except Exception as e:
            raise AnsibleFilterError(str(e)) from e
