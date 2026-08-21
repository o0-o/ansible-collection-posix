#!/usr/bin/python
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

DOCUMENTATION = r"""
---
module: process
short_description: Gather process information from POSIX systems
version_added: "2.0.0"
description:
  - Gathers process information using ps command with jc parsing.
  - >-
    Provides structured process data including PID, executable,
    arguments, and resource usage.
  - Supports filtering by PID or executable path.
options:
  pid:
    description:
      - Filter processes by PID(s).
      - Can be a single PID or list of PIDs.
    type: raw
    required: false
  executable:
    description:
      - Filter processes by executable path or basename.
      - Matches against the full executable path.
    type: str
    required: false
notes:
  - This module is implemented entirely as an action plugin.
  - All logic is handled on the controller side.
seealso:
  - module: ansible.builtin.command
    description: Execute commands on targets
author:
  - oØ.o (@o0-o)
"""

EXAMPLES = r"""
- name: Get all processes
  o0_o.posix.process:
  register: all_processes

- name: Get process by PID
  o0_o.posix.process:
    pid: 1234
  register: process_info

- name: Get processes by executable
  o0_o.posix.process:
    executable: sshd
  register: sshd_processes
"""

RETURN = r"""
processes:
  description: List of process information dictionaries
  returned: always
  type: list
  elements: dict
  contains:
    pid:
      description: Process ID
      type: int
      returned: always
    ppid:
      description: Parent process ID
      type: int
      returned: always
    executable:
      description: Full path to the executable
      type: str
      returned: always
    arguments:
      description: Command line arguments
      type: str
      returned: always
    time:
      description: Time information for the process
      type: dict
      returned: always
      contains:
        elapsed:
          description: Elapsed time since process started
          type: dict
          returned: always
          contains:
            seconds:
              description: Elapsed time in seconds
              type: int
            pretty:
              description: Human-readable elapsed time
              type: str
            iso8601:
              description: ISO 8601 duration format
              type: str
"""


def main():
    """Module stub - all logic is in the action plugin."""
    from ansible.module_utils.basic import AnsibleModule

    module = AnsibleModule(
        argument_spec={
            "pid": {"type": "raw", "required": False},
            "executable": {"type": "str", "required": False},
        },
        supports_check_mode=True,
    )

    # This module is only a stub - all logic is in the action plugin
    # The action plugin intercepts execution before this module runs
    module.exit_json(changed=False, processes=[])


if __name__ == "__main__":
    main()
