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

"""Jinja2 tests for standards compliance."""

from __future__ import annotations

from typing import Any, Dict

from ansible_collections.o0_o.posix.plugins.module_utils import (
    is_posix as is_posix_check,
)

DOCUMENTATION = r"""
---
name: posix
author: oØ.o (@o0-o)
version_added: "1.4.0"
short_description: Test if a system is POSIX-compliant
description:
  - Tests whether a system is POSIX-compliant based on compliance
    information.
  - Returns C(true) if the system is POSIX-compliant, C(false) if it
    is not, or C(none) if compliance cannot be determined.
  - Useful for conditionally executing tasks based on POSIX compliance.
options:
  _input:
    description:
      - Facts dictionary (C(ansible_facts)), registered result from
        C(o0_o.posix.compliance), or compliance dict directly.
      - Can be a dict with C(o0_os.compliance), C(compliance) key, or a
        compliance dict itself.
    type: dict
    required: true
notes:
  - The test can accept a dict with a C(compliance) key or a compliance
    dict directly.
  - A system is considered POSIX-compliant if it has POSIX.1 (XSH),
    POSIX.2 (XCU), or SUS compliance information.
  - Returns C(none) if compliance information is missing or cannot be
    evaluated.
  - Raises C(TypeError) if the input is not a dictionary.
"""

EXAMPLES = r"""
# Check if current host is POSIX-compliant using facts module
- name: Gather POSIX facts
  o0_o.posix.facts:

- name: Run task only on POSIX systems
  ansible.builtin.debug:
    msg: "System is POSIX-compliant"
  when: ansible_facts is posix

# Or use registered result from compliance module
- name: Gather compliance information
  o0_o.posix.compliance:
  register: compliance_result

- name: Check with registered result directly
  ansible.builtin.debug:
    msg: "System is POSIX-compliant"
  when: compliance_result is posix

# Or use the compliance dict directly
- name: Check with compliance dict
  ansible.builtin.debug:
    msg: "POSIX compliant"
  when: compliance_result.compliance is posix

# Check compliance of another host
- name: Check if remote host is POSIX-compliant
  ansible.builtin.debug:
    msg: "Host {{ item }} is POSIX-compliant"
  loop: "{{ groups['all'] }}"
  when: hostvars[item] is posix

# Handle None case (cannot determine)
- name: Check POSIX compliance with fallback
  ansible.builtin.debug:
    msg: >-
      POSIX status:
      {{ 'compliant' if (ansible_facts is posix)
         else 'non-compliant' if (ansible_facts is posix) is not none
         else 'unknown' }}

# Use with block for POSIX-specific tasks
- name: POSIX-specific operations
  block:
    - name: Use POSIX grep
      ansible.builtin.command: grep -r "pattern" /var/log

    - name: Use POSIX find
      ansible.builtin.command: find /tmp -name "*.tmp"
  when: ansible_facts is posix
"""

RETURN = r"""
_value:
  description:
    - C(true) if the system is POSIX-compliant
    - C(false) if the system is not POSIX-compliant
    - C(none) if compliance cannot be determined
  type: bool
  returned: always
"""


class TestModule:
    """Jinja2 test module for standards compliance."""

    def tests(self) -> Dict[str, Any]:
        """Return the test functions."""
        return {"posix": is_posix_check}
