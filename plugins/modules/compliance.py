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

from __future__ import absolute_import, division, print_function
from __future__ import annotations


DOCUMENTATION = r"""
---
module: compliance
short_description: Check POSIX and UNIX standards compliance
version_added: "1.4.0"
description:
  - Tests whether the target system is POSIX-compliant by checking for
    POSIX and X/Open compliance using getconf commands.
  - Returns detailed compliance information in the C(compliance) key.
  - Use the C(posix) Jinja2 test to check if the system is
    POSIX-compliant based on the returned compliance data.
  - Does not require Python on the target host.
options:
  gather:
    description:
      - When true, also sets compliance data in ansible_facts.o0_os.compliance.
      - This allows the compliance data to be used by subsequent tasks via
        ansible_facts without needing to register the result.
    type: bool
    default: false
author:
  - oØ.o (@o0-o)
notes:
  - The module tries multiple methods to determine POSIX compliance.
  - First attempts to use getconf to check _POSIX_VERSION, _POSIX2_VERSION,
    _XOPEN_UNIX, and _XOPEN_VERSION.
  - Falls back to checking the kernel name with uname if getconf is not
    available.
  - This module always returns changed=false as it only tests the system.
attributes:
  check_mode:
    description: This module supports check mode.
    support: full
  async:
    description: This module does not support async operation.
    support: none
  platform:
    description: Only POSIX platforms are supported.
    support: full
    platforms: posix
"""

EXAMPLES = r"""
- name: Check system standards compliance
  o0_o.posix.compliance:
  register: posix_compliance

- name: Gather compliance as ansible_facts
  o0_o.posix.compliance:
    gather: true

- name: Use compliance facts in subsequent tasks
  ansible.builtin.debug:
    msg: >-
      POSIX support:
      {{ ansible_facts['o0_os']['compliance']['posix']['supported'] }}

- name: Set compliance facts (alternative to gather option)
  ansible.builtin.set_fact:
    compliance: "{{ posix_compliance.compliance }}"

- name: Display POSIX compliance status
  ansible.builtin.debug:
    msg: "System is POSIX-compliant: {{ ansible_facts is posix }}"

- name: Run POSIX-specific task only if compliant
  o0_o.posix.command:
    argv: [grep, -E, "pattern", /etc/passwd]
  when: ansible_facts is posix

- name: Skip tasks on non-POSIX systems
  block:
    - name: Gather POSIX facts
      o0_o.posix.facts:

    - name: Run POSIX commands
      o0_o.posix.command:
        cmd: find /var -name "*.log"
  when: ansible_facts is posix
"""

RETURN = r"""
ansible_facts:
  description: >-
    Ansible facts set when gather=true. Contains o0_os.compliance with
    the same structure as the compliance return value.
  returned: when gather=true
  type: dict
  contains:
    o0_os:
      description: Operating system facts namespace
      type: dict
      contains:
        compliance:
          description: >-
            Compliance data (same structure as compliance return value)
          type: dict
compliance:
  description: >-
    Dictionary of compliance standards detected. Contains top-level keys for
    each standard (xsh, xcu, xsi, posix, sus) with their support status.
  returned: always
  type: dict
  contains:
    xsh:
      description: POSIX System Interfaces (XSH) compliance
      type: dict
      contains:
        name:
          description: Full name of the standard
          type: str
          sample: "System Interfaces"
        abbreviation:
          description: Common abbreviation
          type: str
          sample: "XSH"
        description:
          description: Description of the standard
          type: str
          sample: "POSIX System Interfaces and Headers"
        supported:
          description: Whether XSH is supported
          type: bool
          sample: true
        version:
          description: Version information (when supported)
          type: dict
          contains:
            id:
              description: Year identifier
              type: str
              sample: "2008"
            name:
              description: Full version name
              type: str
              sample: "POSIX.1-2008"
        canaries:
          description: Raw getconf values for verification
          type: dict
          sample:
            getconf:
              _POSIX_VERSION: "200809"
    xcu:
      description: POSIX Shell and Utilities (XCU) compliance
      type: dict
      contains:
        name:
          description: Full name of the standard
          type: str
          sample: "Shell & Utilities"
        abbreviation:
          description: Common abbreviation
          type: str
          sample: "XCU"
        description:
          description: Description of the standard
          type: str
          sample: "POSIX Shell and Utilities"
        supported:
          description: Whether XCU is supported
          type: bool
          sample: true
        version:
          description: Version information (when supported)
          type: dict
          contains:
            id:
              description: Year identifier
              type: str
              sample: "2008"
            name:
              description: Full version name
              type: str
              sample: "POSIX.1-2008"
        canaries:
          description: Raw getconf values for verification
          type: dict
          sample:
            getconf:
              _POSIX2_VERSION: "200809"
    xsi:
      description: X/Open System Interfaces (XSI) extensions
      type: dict
      contains:
        name:
          description: Full name of the standard
          type: str
          sample: "X/Open System Interfaces"
        abbreviation:
          description: Common abbreviation
          type: str
          sample: "XSI"
        description:
          description: Description of the standard
          type: str
          sample: "SUS X/Open System Interfaces (UNIX extensions to POSIX)"
        supported:
          description: Whether XSI is supported
          type: bool
          sample: true
        version:
          description: Version information (when supported)
          type: dict
          contains:
            issue:
              description: X/Open Issue number
              type: float
              sample: 7.0
            pretty:
              description: Human-readable issue string
              type: str
              sample: "Issue 7"
        canaries:
          description: Raw getconf values for verification
          type: dict
          sample:
            getconf:
              _XOPEN_UNIX: "1"
              _XOPEN_VERSION: "700"
    posix:
      description: Overall POSIX compliance (requires XSH + XCU)
      type: dict
      contains:
        name:
          description: Full name of the standard
          type: str
          sample: "Portable Operating System Interface"
        abbreviation:
          description: Common abbreviation
          type: str
          sample: "POSIX"
        description:
          description: Description of the standard
          type: str
          sample: "IEEE standard for compatibility between operating systems"
        supported:
          description: >-
            Whether POSIX is supported. Can be true, false, or "partial" if
            only XSH or XCU is supported.
          type: raw
          sample: true
    sus:
      description: Single UNIX Specification compliance (requires POSIX + XSI)
      type: dict
      contains:
        name:
          description: Full name of the standard
          type: str
          sample: "Single UNIX Specification"
        abbreviation:
          description: Common abbreviation
          type: str
          sample: "SUS"
        description:
          description: Description of the standard
          type: str
          sample: "Unified UNIX standard combining POSIX with XSI extensions"
        supported:
          description: Whether SUS is supported
          type: bool
          sample: true
        version:
          description: Version information (when supported)
          type: dict
          contains:
            issue:
              description: X/Open Issue number
              type: float
              sample: 7.0
            id:
              description: SUS version number
              type: int
              sample: 4
            pretty:
              description: Human-readable version string
              type: str
              sample: "v4"
shells:
  description: >-
    Dictionary mapping shell paths to their properties, including detected
    builtins.
  returned: always
  type: dict
  sample:
    /bin/sh:
      builtins:
        - command
        - test
        - "["
paths:
  description: Dictionary of command paths found on the system
  returned: always
  type: dict
  sample:
    /bin/cat: {}
    /usr/bin/grep: {}
    /bin/sh: {}
missing_commands:
  description: List of required commands not found on the system
  returned: always
  type: list
  elements: str
  sample: []
msg:
  description: Human-readable message about the compliance status
  returned: always
  type: str
  sample: "System is SUS-compliant (v4)"
changed:
  description: Always false as this module only tests the system
  returned: always
  type: bool
  sample: false
"""

from ansible.module_utils.basic import AnsibleModule


def main() -> None:
    """Fail if this module is run directly without the action plugin."""
    argument_spec = {
        "gather": {
            "type": "bool",
            "default": False,
        },
    }

    module = AnsibleModule(
        argument_spec=argument_spec, supports_check_mode=True
    )
    module.fail_json(msg="This module must be run via its action plugin.")


if __name__ == "__main__":
    main()
