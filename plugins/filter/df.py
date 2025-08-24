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
name: df
short_description: Parse df command output
version_added: "1.4.0"
description:
  - Parse output from the df command into structured data using jc
  - Can return either raw jc format or simplified facts structure
  - When used with facts=True, returns filesystems keyed by mount point
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
      - Returns structure with filesystems keyed by mount point
    type: bool
    default: false
requirements:
  - jc (Python library)
notes:
  - The jc library handles various df output formats (df, df -h, df -k, etc.)
  - Field names vary based on block size (1024_blocks, 512_blocks, size)
  - When facts=True, mount point is used as key and removed from entry data
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
    msg: "Root filesystem is {{ fs_info.filesystems['/'].use_percent }}% full"
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
filesystems:
  description: Filesystems keyed by mount point
  type: dict
  returned: always
  sample:
    /:
      filesystem: /dev/disk1s1
      1024_blocks: 488245288
      used: 305659284
      available: 180530392
      use_percent: 63
    /System/Volumes/VM:
      filesystem: /dev/disk1s4
      1024_blocks: 488245288
      used: 5369176
      available: 180530392
      use_percent: 3
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
        :returns: Facts structure with filesystems keyed by mount point
        """
        filesystems = {}
        for entry in parsed:
            # Make a copy to avoid modifying the original
            entry_copy = entry.copy()
            mount_point = entry_copy.pop("mounted_on", None)
            if mount_point:
                filesystems[mount_point] = entry_copy

        return {"filesystems": filesystems}

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
