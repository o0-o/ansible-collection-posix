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
from ansible_collections.o0_o.posix.plugins.filter_utils import JCBase

try:
    from ansible_collections.o0_o.utils.plugins.filter import SiFilter

    HAS_SI_FILTER = True
    _si_filter = SiFilter()
except ImportError:
    HAS_SI_FILTER = False
    _si_filter = None

DOCUMENTATION = r"""
---
name: df
short_description: Parse df command output
version_added: "1.4.0"
description:
  - Parse output from the df command into structured data using jc
  - Can return either raw jc format or simplified facts structure
  - When used with facts=True, returns mounts keyed by mount point with
    structured capacity information
options:
  _input:
    description:
      - Command output from 'df' as string, list of lines, or
        command result dict
    type: raw
    required: true
  facts:
    description:
      - If True, format output for direct merge into Ansible facts
      - Returns structure with mounts keyed by mount point
    type: bool
    default: false
requirements:
  - jc (Python library)
  - o0_o.utils collection (required for facts=True)
notes:
  - The jc library handles various df output formats (df, df -h, df -k, etc.)
  - Field names vary based on block size (1024_blocks, 512_blocks, size)
  - When facts=True, mount point is used as key and removed from entry data
  - When facts=True, capacity values are provided in both bytes and
    human-readable format
author:
  - oØ.o (@o0-o)
"""

EXAMPLES = r"""
# Parse df output
- name: Get filesystem usage
  ansible.builtin.command:
    cmd: df -h
  register: df_result

- name: Parse df output
  ansible.builtin.debug:
    msg: "{{ df_result.stdout | o0_o.posix.df }}"

# Use facts format for structured data
- name: Parse for facts
  ansible.builtin.set_fact:
    fs_info: "{{ df_result.stdout | o0_o.posix.df(facts=true) }}"

- name: Display root filesystem usage
  ansible.builtin.debug:
    msg: "Root uses {{ fs_info.mounts['/'].capacity.used.pretty }}"
"""

RETURN = r"""
# When facts=False (default)
_output:
  description: List of filesystem entries from jc parser
  type: list
  elements: dict
  returned: always
  sample:
    - filesystem: /dev/disk1s1
      1024_blocks: 488245288
      used: 305659284
      available: 180530392
      use_percent: 63
      mounted_on: /
    - filesystem: /dev/disk1s4
      1024_blocks: 488245288
      used: 5369176
      available: 180530392
      use_percent: 3
      mounted_on: /System/Volumes/VM

# When facts=True
mounts:
  description: Mounts keyed by mount point with structured capacity data
  type: dict
  returned: always
  sample:
    /:
      device: /dev/disk1s1
      capacity:
        total:
          bytes: 499963174912
          pretty: "465.6 GiB"
        used:
          bytes: 313155427328
          pretty: "291.6 GiB"
    /System/Volumes/VM:
      device: /dev/disk1s4
      capacity:
        total:
          bytes: 499963174912
          pretty: "465.6 GiB"
        used:
          bytes: 5498036224
          pretty: "5.1 GiB"
"""


class FilterModule(JCBase):
    """Filter for parsing df command output using jc."""

    def filters(self) -> Dict[str, Any]:
        """Return the filter functions."""
        return {
            "df": self.df,
        }

    def _format_as_facts(self, parsed: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Format parsed df data for Ansible facts structure.

        :param parsed: List of filesystem dictionaries from jc
        :returns: Facts structure with mounts keyed by mount point
        """
        if not HAS_SI_FILTER:
            raise AnsibleFilterError(
                "The 'facts' mode requires the o0_o.utils collection. "
                "Please install it with: "
                "ansible-galaxy collection install o0_o.utils"
            )
        mounts = {}
        for entry in parsed:
            mount_point = entry.get("mounted_on")
            if not mount_point:
                raise AnsibleFilterError(
                    "df output missing 'mounted_on' field for entry: "
                    f"{entry}"
                )

            mount_data = {}

            # Handle source field (device for /dev paths, source for network)
            if "filesystem" in entry:
                source = entry["filesystem"]
                if source.startswith("/dev/"):
                    mount_data["device"] = source
                elif ":" in source or source.startswith("//"):
                    # Network filesystem (NFS, CIFS/SMB)
                    mount_data["source"] = source

            # Add capacity information if available
            capacity = {}

            blocks_field = None
            blocks_multiplier = None
            capacity_total = None
            used_total = None

            # Define the block size
            for key in entry.keys():
                if key.endswith("_blocks"):
                    blocks_field = key
                    # Extract the multiplier from field name
                    # (e.g., "512_blocks" -> 512)
                    blocks = key.replace("_blocks", "")
                    # Handle formats: 512, 1024, 1k, 1K, 1M, etc.
                    if blocks.isdigit():
                        blocks_multiplier = int(blocks)
                        unit = "B"
                    else:
                        # Parse size units like 1K, 1M, 1G
                        match = re.match(r"^(\d+)([a-zA-Z]+)$", blocks)
                        if match:
                            blocks_multiplier = int(match.group(1))
                            unit = f"{match.group(2).upper()}iB"
                        else:
                            raise AnsibleFilterError(
                                f"Unable to parse block size format: {blocks}"
                            )
                    break

            # Define parsable used and total sizes
            if (
                blocks_field
                and blocks_multiplier
                and blocks_field in entry
                and entry[blocks_field] is not None
            ):
                capacity_total = (
                    f"{entry[blocks_field] * blocks_multiplier}{unit}"
                )
                if "used" in entry and entry["used"] is not None:
                    used_total = f"{entry['used'] * blocks_multiplier}{unit}"
            else:
                if entry.get("size"):
                    capacity_total = entry["size"]
                if entry.get("used"):
                    # Check if it's a string with units (like "5.1G")
                    # vs just a number
                    if (
                        isinstance(entry["used"], str)
                        and not entry["used"].isdigit()
                    ):
                        used_total = entry["used"]

            # Calculate total capacity
            if capacity_total:
                # Add B suffix if not present (for plain numbers)
                if isinstance(capacity_total, str) and capacity_total.isdigit():
                    capacity_total = capacity_total + "B"
                parsed = _si_filter.si(capacity_total, binary=True)
                capacity_bytes = parsed.get("bytes", 0)
                capacity_pretty = parsed.get("pretty", capacity_total)
                capacity["total"] = {
                    "bytes": capacity_bytes,
                    "pretty": capacity_pretty,
                }

            # Calculate used capacity
            if used_total:
                # Add B suffix if not present (for plain numbers)
                if isinstance(used_total, str) and used_total.isdigit():
                    used_total = used_total + "B"
                # Used field uses same multiplier as blocks field
                parsed = _si_filter.si(used_total, binary=True)
                used_bytes = parsed.get("bytes", 0)
                used_pretty = parsed.get("pretty", used_total)
                capacity["used"] = {
                    "bytes": used_bytes,
                    "pretty": used_pretty,
                }

            if capacity:
                mount_data["capacity"] = capacity

            mounts[mount_point] = mount_data

        return {"mounts": mounts}

    def df(
        self,
        data: Union[str, List[str], Dict[str, Any]],
        facts: bool = False,
    ) -> Union[List[Dict[str, Any]], Dict[str, Any]]:
        """Parse df output into structured data using jc.

        :param data: Output from df command - string, list of lines, or
            command result
        :param facts: If True, format for direct merge into Ansible
            facts
        :returns: List of filesystem dictionaries from jc, or facts
            structure
        """
        # Get parsed data from jc
        parsed = self.parse_command(data, "df")

        if not facts:
            # Return jc's parsed format directly
            return parsed

        # Format for facts module
        return self._format_as_facts(parsed)
