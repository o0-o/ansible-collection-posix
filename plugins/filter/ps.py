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
from ansible.module_utils.common.text.converters import to_native
from ansible_collections.o0_o.posix.plugins.module_utils import ps

DOCUMENTATION = r"""
---
name: ps
short_description: Parse ps command output
version_added: "1.2.0"
description:
  - Parse output from the ps command into structured data using jc
  - Returns a list of process entries with organized nested fields
  - Unidirectional filter (parse only, no generation)
options:
  _input:
    description:
      - Command output from 'ps' as string or command result dict
      - Must be ps output that jc can parse
    type: raw
    required: true
requirements:
  - jc (Python library)
notes:
  - The jc library parses ps output into structured data
  - Restructures data with nested time, processor, and memory dicts
  - Converts uid/gid to integers
  - Splits command into executable and arguments
  - Parses time fields with parse_elapsed_time and parse_datetime
  - Parses memory fields with parse_si
  - Only includes fields that jc provides in the output
  - Unknown fields are quietly excluded
author:
  - oØ.o (@o0-o)
"""

EXAMPLES = r"""
# Parse ps output
- name: Get process information
  ansible.builtin.command:
    cmd: ps -ax -o pid,ppid,uid,gid,etime,time,lstart,pcpu,pmem,rss,vsz,command
  register: ps_result

- name: Parse ps output and store
  ansible.builtin.set_fact:
    processes: "{{ ps_result.stdout | o0_o.posix.ps }}"

- name: Display process with PID 1
  vars:
    init_proc: "{{ processes | selectattr('pid', 'equalto', 1) | first }}"
  ansible.builtin.debug:
    msg: >-
      Init process {{ init_proc.executable }} has been running for
      {{ init_proc.time.elapsed.pretty }}
"""

RETURN = r"""
_value:
  description: List of process entries with standardized nested structure
  type: list
  elements: dict
  returned: always
  sample:
    - pid: 1
      ppid: 0
      uid: 0
      gid: 0
      executable: /sbin/init
      arguments: --system-mode
      time:
        elapsed:
          seconds: 608426
          pretty: 7 days, 1 hour, 20 minutes, 26 seconds
          iso8601: P7DT1H20M26S
        started:
          seconds: 1739567890
          pretty: Tuesday, February 14, 2025, 10:31:30 p.m. UTC
          iso8601: 2025-02-14T22:31:30Z
      processor:
        time:
          seconds: 3459
          pretty: 57 minutes, 39 seconds
          iso8601: PT57M39S
        percent: 0.1
      memory:
        real:
          bytes: 31457280
          pretty: 30 MiB
          percent: 1.2
        virtual:
          bytes: 104857600
          pretty: 100 MiB
"""


class FilterModule:
    """Filter for parsing ps command output."""

    def filters(self) -> Dict[str, Any]:
        """Return the filter functions."""
        return {"ps": self.ps_filter}

    def ps_filter(
        self,
        config: Union[str, Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Parse ps output into structured data.

        Parses ps command output into normalized list of entries with:
        - Basic fields: pid, ppid, uid (int), gid (int), executable, arguments
        - time: dict with elapsed and started (parsed)
        - processor: dict with time and percent
        - memory: dict with real and virtual (parsed with SI units)

        Only fields available from jc output are included. Unknown fields
        are quietly excluded.

        :param config: ps command output as string or dict
        :returns: List of process entries with standardized structure
        :raises AnsibleFilterError: If parsing fails
        """
        try:
            return ps(config)
        except (ValueError, ImportError) as e:
            raise AnsibleFilterError(
                f"ps failed: {type(e).__name__}: {to_native(e)}"
            ) from e
