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

__metaclass__ = type

DOCUMENTATION = r"""
---
module: run
short_description: Execute multiple commands in a single SSH round trip
version_added: "1.5.0"
description:
  - Executes multiple commands on the remote host in a single batched
    operation to minimize SSH latency.
  - Each command's return code, stdout, and stderr are captured and
    returned separately in the results list.
  - Commands are executed in subshells with output redirected to
    temporary files, then parsed using length-prefix format for
    accurate handling of binary or multiline output.
  - Dramatically reduces latency compared to executing commands
    individually (20-30 round trips reduced to 1).
options:
  commands:
    description:
      - List of commands to execute.
      - Each command can be a string (executed as-is) or a list of
        arguments (properly quoted for shell execution).
    type: list
    elements: raw
    required: true
  chdir:
    description:
      - Change to this directory before executing each command.
      - Each command is executed in a subshell so directory changes
        do not affect subsequent commands.
    type: path
  creates:
    description:
      - Path to a file or directory.
      - If it already exists, this step will be skipped.
    type: path
  removes:
    description:
      - Path to a file or directory.
      - If it does not exist, this step will be skipped.
    type: path
  parallel:
    description:
      - Execute commands in parallel using background jobs.
      - When C(true), all commands are launched simultaneously and
        results are collected after all complete.
      - When C(false), commands execute sequentially in order.
      - Defaults to the inverse of I(fail_fast) (i.e., C(true) unless
        I(fail_fast=true)).
      - Mutually exclusive with I(fail_fast).
    type: bool
  fail_fast:
    description:
      - Stop executing remaining commands if any command fails.
      - When C(false), all commands execute regardless of failures.
      - Only valid for sequential execution (I(parallel=false)).
      - Mutually exclusive with I(parallel).
    type: bool
    default: false
  strip:
    description:
      - Strip trailing whitespace from stdout and stderr of each command.
      - When C(true), trailing newlines and spaces are removed.
    type: bool
    default: true
  raw:
    description:
      - Control raw execution mode behavior.
      - 'C(true): Force raw fallback mode, bypassing native Python.'
      - 'C(false): Force native Python execution (fail if unavailable).'
      - 'C("auto"): Automatically detect and use the best method.'
    type: raw
    default: "auto"
author:
  - oØ.o (@o0-o)
notes:
  - This module is implemented as an action plugin and supports raw
    fallback.
  - Commands are executed in the order provided.
  - Each command runs in its own subshell for isolation.
seealso:
  - module: ansible.builtin.command
    description: Execute commands on targets
  - module: ansible.builtin.shell
    description: Execute shell commands on targets
"""

EXAMPLES = r"""
- name: Execute multiple system information commands
  o0_o.posix.run:
    commands:
      - uname -s
      - uname -m
      - uptime
  register: sysinfo_reg

- name: Display command results
  ansible.builtin.debug:
    msg: "{{ item['stdout'] }}"
  loop: "{{ sysinfo_reg['commands'] }}"

- name: Execute commands with argument lists for safe quoting
  o0_o.posix.run:
    commands:
      - [cat, /path/with spaces/file.txt]
      - [echo, "quoted string"]
      - ls -la
  register: mixed_reg

- name: Execute commands in specific directory
  o0_o.posix.run:
    commands:
      - pwd
      - ls -la
      - cat README.md
    chdir: /etc/ssh
  register: ssh_config_reg

- name: Stop on first failure (sequential mode)
  o0_o.posix.run:
    commands:
      - test -f /etc/hosts
      - cat /etc/hosts
      - grep localhost /etc/hosts
    parallel: false
    fail_fast: true
  register: hosts_check_reg

- name: Skip if file already exists
  o0_o.posix.run:
    commands:
      - curl -o /tmp/download.txt https://example.com/file.txt
    creates: /tmp/download.txt

- name: Only run if directory exists
  o0_o.posix.run:
    commands:
      - find . -name "*.log" -delete
    removes: /var/log/app
"""

RETURN = r"""
changed:
  description: Whether any commands were executed
  returned: always
  type: bool
  sample: true
failed:
  description: Whether any command failed (rc != 0)
  returned: always
  type: bool
  sample: false
msg:
  description: Summary message about execution
  returned: always
  type: str
  sample: "Executed 3 commands"
commands:
  description: >-
    Command results in execution order.
    Returns a list when input is a list, or a dict when input is a dict
    (keys preserved).
  returned: success
  type: raw
  contains:
    rc:
      description: Return code from the command
      type: int
      sample: 0
    stdout:
      description: Standard output from the command
      type: str
      sample: "Linux"
    stderr:
      description: Standard error from the command
      type: str
      sample: ""
    stdout_lines:
      description: Standard output split into lines
      type: list
      elements: str
      sample: ["Linux"]
    stderr_lines:
      description: Standard error split into lines
      type: list
      elements: str
      sample: []
    elapsed:
      description: Time taken to execute the command
      type: str
      sample: "0:00:01"
raw:
  description: Whether raw fallback mode was used
  returned: always
  type: bool
  sample: false
skipped:
  description: Whether execution was skipped
  returned: when skipped
  type: bool
  sample: false
skip_reason:
  description: Reason for skipping execution
  returned: when skipped
  type: str
  sample: "Skipped because /tmp/file exists"
"""
from ansible.module_utils.basic import AnsibleModule


def main() -> None:
    """Fail if this module is run directly without the action plugin."""

    argument_spec = {
        "commands": {
            "type": "list",
            "elements": "raw",
            "required": True,
        },
        "chdir": {"type": "path"},
        "creates": {"type": "path"},
        "removes": {"type": "path"},
        "parallel": {"type": "bool"},  # Default derived from fail_fast
        "fail_fast": {"type": "bool", "default": False},
        "strip": {"type": "bool", "default": True},
        "raw": {"type": "raw", "default": "auto"},
    }
    mutually_exclusive = [["parallel", "fail_fast"]]

    module = AnsibleModule(
        argument_spec=argument_spec,
        mutually_exclusive=mutually_exclusive,
        supports_check_mode=True,
    )
    module.fail_json(msg="This module must be run via its action plugin.")


if __name__ == "__main__":
    main()
