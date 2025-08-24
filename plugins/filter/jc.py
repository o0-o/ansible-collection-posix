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

from typing import Any, Dict

from ansible_collections.o0_o.posix.plugins.filter_utils import JCBase

DOCUMENTATION = r"""
name: jc
version_added: "1.4.0"
short_description: Parse command output using jc library
description:
  - Parse various command outputs into structured JSON data using the jc library
  - Supports parsing output from common Unix commands like ps, df, mount, etc.
  - See U(https://github.com/kellyjonbrazil/jc) for list of supported parsers
options:
  _input:
    description:
      - Command output to parse - string, list of lines, or command result dict
    type: raw
    required: true
  parser:
    description:
      - Name of the jc parser to use (e.g., 'ps', 'df', 'mount', 'uname')
      - Run 'jc --help' or visit jc documentation for complete list
    type: str
    required: true
  raw:
    description:
      - If True, return raw parsed output without post-processing
      - Some parsers provide additional normalization when False
    type: bool
    default: false
  quiet:
    description:
      - If True, suppress jc parsing warnings
    type: bool
    default: false
requirements:
  - jc (Python library)
author:
  - oØ.o (@o0-o)
"""

EXAMPLES = r"""
# Parse ps aux output
- name: Get process list
  ansible.builtin.command:
    cmd: ps aux
  register: ps_result

- name: Parse ps output
  ansible.builtin.debug:
    msg: "{{ ps_result.stdout | o0_o.posix.jc('ps') }}"

# Parse df output
- name: Get filesystem info
  ansible.builtin.command:
    cmd: df -h
  register: df_result

- name: Parse df output with raw format
  ansible.builtin.debug:
    msg: "{{ df_result | o0_o.posix.jc('df', raw=true) }}"

# Parse mount output
- name: Get mount points
  ansible.builtin.command:
    cmd: mount
  register: mount_result

- name: Parse mount output quietly
  ansible.builtin.debug:
    msg: "{{ mount_result.stdout_lines | o0_o.posix.jc('mount', quiet=true) }}"
"""

RETURN = r"""
_output:
  description:
    - Parsed data structure varies based on the parser used
    - Most parsers return a list of dictionaries
    - Some parsers return a single dictionary
  type: raw
  returned: success
  sample: |
    [
      {
        "user": "root",
        "pid": 1,
        "cpu_percent": 0.0,
        "mem_percent": 0.1,
        "command": "/sbin/init"
      }
    ]
"""


class FilterModule(JCBase):
    """Generic filter for parsing command output using jc."""

    def filters(self) -> Dict[str, Any]:
        """Return the filter functions."""
        return {
            "jc": self.jc,
        }
