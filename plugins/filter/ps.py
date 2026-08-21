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
from ansible_collections.o0_o.posix.plugins.module_utils import ps

DOCUMENTATION = r"""
---
name: ps
short_description: Parse ps command output
version_added: "2.0.0"
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
  - Restructures data with nested time, processor, memory, and status
    dicts
  - Renames C(pid) to C(id) and C(ppid) to C(parent)
  - Reports the owning user as C(owner) and the owning group as
    C(group), as integers when ps prints numeric ids and as names when
    it only prints names
  - Keeps the whole command line as C(title) without splitting it,
    because a process can rewrite its own title through
    C(setproctitle())
  - Parses time fields with parse_elapsed_time and parse_datetime
  - Parses memory fields with parse_si
  - Only includes fields that jc provides in the output
  - Unknown fields are quietly excluded
author:
  - oØ.o (@o0-o)
"""

EXAMPLES = r"""
# Parse ps output
# lstart is deliberately absent: it contains spaces, which leaves jc
# unable to tell where the start time ends and the command begins.
# time.started is derived from etime instead.
- name: Get process information
  ansible.builtin.command:
    cmd: ps -axww -o pid,ppid,uid,gid,etime,time,stat,pcpu,pmem,rss,vsz,command
  register: ps_result

- name: Parse ps output and store
  ansible.builtin.set_fact:
    processes: "{{ ps_result.stdout | o0_o.posix.ps }}"

- name: Display process with PID 1
  vars:
    init_proc: "{{ processes | selectattr('id', 'equalto', 1) | first }}"
  ansible.builtin.debug:
    msg: >-
      Init process {{ init_proc.title }} has been running for
      {{ init_proc.time.elapsed.pretty }}

- name: List the sleeping processes owned by root
  ansible.builtin.debug:
    msg: >-
      {{ processes
         | selectattr('owner', 'equalto', 0)
         | selectattr('status.state', 'equalto', 'sleeping')
         | map(attribute='title')
         | list }}
"""

RETURN = r"""
_value:
  description:
    - List of process entries with standardized nested structure.
    - Every entry carries C(id) and C(parent). Each remaining field
      appears only when ps printed the column it comes from, so the
      entry shape follows the C(-o) format the command was given.
  type: list
  elements: dict
  returned: always
  contains:
    id:
      description: Process ID, C(null) when ps printed no PID column
      type: int
      sample: 1
    parent:
      description: >-
        Parent process ID, C(null) when ps printed no PPID column
      type: int
      sample: 0
    title:
      description:
        - The process title as ps printed it, command and arguments
          together.
        - Not split into an executable and its arguments; a process can
          rewrite this string through C(setproctitle()), which makes
          any such split unreliable.
      returned: when ps printed a command or args column
      type: str
      sample: /sbin/init
    owner:
      description: >-
        Owning user, the numeric UID where ps printed one and the
        username where it printed only a name
      returned: when ps printed a uid or user column
      type: raw
      sample: 0
    group:
      description: >-
        Owning group, the numeric GID where ps printed one and the
        group name where it printed only a name
      returned: when ps printed a gid or group column
      type: raw
      sample: 0
    time:
      description: Wall-clock times for the process
      returned: when ps printed an etime or elapsed column
      type: dict
      contains:
        elapsed:
          description: How long the process has been running
          type: dict
          sample:
            seconds: 609626
            pretty: 7 days, 1 hour, 20 minutes, 26 seconds
            iso8601: P7DT1H20M26S
        started:
          description:
            - When the process started, derived by subtracting
              C(elapsed) from the controller's current time.
            - A point in time, so it carries no C(iso8601) duration.
          returned: >-
            when elapsed parsed and the start time is inside the
            representable date range
          type: dict
          sample:
            seconds: 1786677802
            pretty: Thursday, August 13, 2026, 11:23:22 p.m. UTC-04:00
    processor:
      description: Processor usage for the process
      returned: when ps printed a time, pcpu, or cpu column
      type: dict
      contains:
        time:
          description: Processor time the process has consumed
          returned: >-
            when ps printed a time column in a form the duration parser
            accepts
          type: dict
          sample:
            seconds: 3459
            pretty: 57 minutes, 39 seconds
            iso8601: PT57M39S
        percent:
          description: Percentage of processor time in use
          returned: when ps printed a pcpu column
          type: float
          sample: 0.1
    memory:
      description: Memory usage for the process
      returned: when ps printed an rss or vsz column
      type: dict
      contains:
        real:
          description: Resident set size, with its share of real memory
          returned: when ps printed an rss column
          type: dict
          sample:
            bytes: 31457280
            pretty: 30 MiB
            percent: 1.2
        virtual:
          description: Virtual memory size
          returned: when ps printed a vsz column
          type: dict
          sample:
            bytes: 104857600
            pretty: 100 MiB
    status:
      description: The stat code, decoded
      returned: when ps printed a stat column
      type: dict
      contains:
        id:
          description: The raw stat string
          type: str
          sample: Ss
        state:
          description: >-
            Process state, C(unknown) for a state character this
            collection does not recognize
          type: str
          choices:
            - running
            - sleeping
            - uninterruptible
            - stopped
            - zombie
            - idle
            - exiting
            - paging
            - dead
            - unknown
          sample: sleeping
        leader:
          description: Whether the process is a session leader
          type: bool
          sample: true
        multithreaded:
          description: Whether the process is multi-threaded (BSD)
          type: bool
          sample: false
        foreground:
          description: >-
            Whether the process is in the foreground process group
          type: bool
          sample: false
        priority:
          description: >-
            C(high) for a raised priority, C(low) for a lowered one,
            C(null) when the stat code names neither
          type: str
          sample: null
        locked:
          description: Whether the process has pages locked in memory
          type: bool
          sample: false
"""


class FilterModule:
    """Filter for parsing ps command output."""

    def filters(self) -> dict[str, Any]:
        """Return the filter functions."""
        return {"ps": self.ps_filter}

    def ps_filter(
        self,
        config: Union[str, dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Parse ps output into structured data.

        Parses ps output into normalized list of entries with:
        - Basic: id, parent, owner, group, title
        - time: elapsed (parsed) and started (derived from elapsed)
        - processor: time and percent
        - memory: real and virtual (SI parsed)
        - status: the stat code, decoded

        Only fields from jc output included. Unknown fields are
        quietly excluded.

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
