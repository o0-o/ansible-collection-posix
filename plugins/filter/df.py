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
from ansible_collections.o0_o.posix.plugins.module_utils import df


DOCUMENTATION = r"""
---
name: df
short_description: Parse df command output
version_added: "1.4.0"
description:
  - Parse output from the df command into structured data using jc
  - Returns a list of mount entries with structured capacity information
  - Automatically formats capacity data with bytes and human-readable values
options:
  _input:
    description:
      - Command output from 'df' as string or command result dict
    type: raw
    required: true
requirements:
  - jc (Python library)
  - o0_o.utils collection (for capacity formatting)
notes:
  - The jc library handles various df output formats (df, df -h, df -k, etc.)
  - Field names vary based on block size (1024_blocks, 512_blocks, size)
  - Capacity values are provided in both bytes and human-readable format
  - Returns same base structure as mount filter plus capacity field
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
      Root uses {{ (fs_info | selectattr('mount', 'equalto', '/')
                   | first).capacity.used.pretty }}
      of {{ (fs_info | selectattr('mount', 'equalto', '/')
            | first).capacity.total.pretty }}
      ({{ (fs_info | selectattr('mount', 'equalto', '/')
          | first).capacity.used.percent }}%)
"""

RETURN = r"""
_value:
  description: List of mount entries with structured capacity data
  type: list
  elements: dict
  returned: always
  sample:
    - mount: /
      source: /dev/disk1s1
      capacity:
        total:
          bytes: 499963174912
          pretty: "465.6 GiB"
        used:
          bytes: 313155427328
          pretty: "291.6 GiB"
          percent: 62.6
    - mount: /System/Volumes/VM
      source: /dev/disk1s4
      capacity:
        total:
          bytes: 499963174912
          pretty: "465.6 GiB"
        used:
          bytes: 5498036224
          pretty: "5.1 GiB"
          percent: 1.1
"""


class FilterModule:
    """Filter for parsing df command output."""

    def filters(self) -> dict[str, Any]:
        """Return the filter functions."""
        return {"df": self.df_filter}

    def df_filter(
        self,
        config: Union[str, dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Parse df output into structured data.

        Parses df command output into normalized list of entries with:
        - filesystem → source
        - mounted_on → mount
        - capacity structure with total/used (bytes, pretty, percent)

        :param config: Df command output as string or dict
        :returns: List of df entries with standardized structure
        :raises AnsibleFilterError: If parsing fails
        """
        try:
            return df(config)
        except (ValueError, ImportError) as e:
            raise AnsibleFilterError(
                f"df failed: {type(e).__name__}: {to_native(e)}"
            ) from e
