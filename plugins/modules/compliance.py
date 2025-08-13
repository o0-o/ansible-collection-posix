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

__metaclass__ = type


DOCUMENTATION = r"""
---
module: compliance
short_description: Check POSIX and UNIX standards compliance
version_added: "1.1.0"
description:
  - Tests whether the target system is POSIX-compliant by checking for
    POSIX and X/Open compliance using getconf commands.
  - Returns success with C(is_posix=true) if the system appears to be
    POSIX-compliant, or C(is_posix=false) if it doesn't.
  - Can be used to conditionally execute other POSIX-dependent tasks.
  - Does not require Python on the target host.
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

- name: Display POSIX compliance status
  ansible.builtin.debug:
    msg: "System is POSIX-compliant: {{ posix_compliance.is_posix }}"

- name: Run POSIX-specific task only if compliant
  o0_o.posix.command:
    argv: [grep, -E, "pattern", /etc/passwd]
  when: posix_compliance.is_posix

- name: Skip tasks on non-POSIX systems
  block:
    - name: Gather POSIX facts
      o0_o.posix.facts:

    - name: Run POSIX commands
      o0_o.posix.command:
        cmd: find /var -name "*.log"
  when: posix_compliance.is_posix
"""

RETURN = r"""
is_posix:
  description: Whether the system is POSIX-compliant
  returned: always
  type: bool
  sample: true
compliance:
  description: Dictionary of compliance standards detected
  returned: always
  type: dict
  contains:
    posix:
      description: POSIX compliance information
      returned: when POSIX compliance is detected
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
        components:
          description: POSIX components detected on the system
          returned: when POSIX components are found
          type: dict
          contains:
            xsh:
              description: System Interfaces and Headers compliance
              returned: when _POSIX_VERSION is defined
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
                version:
                  description: Version information
                  type: dict
                  contains:
                    id:
                      description: Version identifier
                      type: str
                      sample: "2008"
                    name:
                      description: Full version name
                      type: str
                      sample: "POSIX.1-2008"
                    getconf:
                      description: Raw values from getconf commands
                      type: dict
                      sample:
                        _POSIX_VERSION: "200809"
            xcu:
              description: Shell and Utilities compliance
              returned: when _POSIX2_VERSION is defined
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
                version:
                  description: Version information
                  type: dict
                  contains:
                    id:
                      description: Version identifier
                      type: str
                      sample: "2008"
                    name:
                      description: Full version name
                      type: str
                      sample: "POSIX.1-2008"
                    getconf:
                      description: Raw values from getconf commands
                        (None if undefined)
                      type: dict
                      sample:
                        _POSIX2_VERSION: "200809"
                        _XOPEN_XCU_VERSION: null
                note:
                  description: Additional information about XCU detection
                  returned: when POSIX2 is assumed from XCU_VERSION
                  type: str
                  sample: |
                    Assuming _POSIX_VERSION (200809) applies because
                    _XOPEN_XCU_VERSION is defined (4) but appears to be invalid
            xsi:
              description: X/Open System Interface extensions
              returned: when _XOPEN_UNIX > 0
              type: dict
              contains:
                name:
                  description: Full name of the standard
                  type: str
                  sample: "X/Open System Interface"
                abbreviation:
                  description: Common abbreviation
                  type: str
                  sample: "XSI"
                description:
                  description: Description of the standard
                  type: str
                  sample: "Extensions to POSIX for UNIX systems"
                enabled:
                  description: Whether XSI extensions are enabled
                  type: bool
                  sample: true
                getconf:
                  description: Raw values from getconf commands
                  type: dict
                  sample:
                    _XOPEN_UNIX: "1"
    sus:
      description: Single UNIX Specification compliance
      returned: when X/Open compliance is detected
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
        version:
          description: Version information
          type: dict
          contains:
            id:
              description: Version identifier
              type: int
              sample: 4
            name:
              description: Full version name
              type: str
              sample: "SUSv4"
            getconf:
              description: Raw values from getconf commands
              type: dict
              sample:
                _XOPEN_VERSION: "700"
        getconf:
          description: Raw values from getconf commands
          type: dict
          sample:
            _XOPEN_UNIX: "1"
msg:
  description: Human-readable message about the compliance status
  returned: always
  type: str
  sample: "System is POSIX-compliant (XSH, XCU, XSI)"
changed:
  description: Always false as this is a test module
  returned: always
  type: bool
  sample: false
"""
