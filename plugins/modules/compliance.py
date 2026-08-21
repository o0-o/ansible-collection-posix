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
  - Read C(compliance.posix.supported) to decide whether the system is
    POSIX-compliant. It answers C(true), C(false), or C("partial") where
    only one of XSH and XCU is supported, so a task that needs full
    compliance tests for C(true) rather than for truthiness.
  - Does not require Python on the target host.
options:
  gather:
    description:
      - When true, also publishes everything this module answers with as
        facts - C(o0_os.compliance), C(o0_os.shells), C(o0_paths) and
        C(o0_missing.commands).
      - This allows the compliance data to be used by subsequent tasks via
        ansible_facts without needing to register the result.
      - The facts are the same values this module returns, under the
        names M(o0_o.posix.facts) publishes them by, because both
        producers share the processor that names them.
    type: bool
    default: false
    version_added: "2.0.0"
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
    msg: >-
      System is POSIX-compliant:
      {{ posix_compliance.compliance.posix.supported }}

- name: Run POSIX-specific task only if fully compliant
  o0_o.posix.command:
    argv: [grep, -E, "pattern", /etc/passwd]
  when: posix_compliance.compliance.posix.supported is true

- name: Skip tasks on non-POSIX systems
  block:
    - name: Gather POSIX facts
      o0_o.posix.facts:

    - name: Run POSIX commands
      o0_o.posix.command:
        cmd: find /var -name "*.log"
  when: ansible_facts.o0_os.compliance.posix.supported is true

- name: Report which utilities a partially compliant host is missing
  ansible.builtin.debug:
    msg: >-
      Missing: {{ posix_compliance.missing_commands | join(', ') }}
  when: posix_compliance.compliance.posix.supported != true
"""

RETURN = r"""
ansible_facts:
  description: >-
    The facts published when C(gather=true) - every value this module
    returns, under the names the shared processor gives them. Nothing
    here is un-prefixed, and nothing this module returns is left out.
  returned: when gather=true
  type: dict
  contains:
    o0_os:
      description: Operating system facts namespace
      type: dict
      contains:
        compliance:
          description: >-
            Compliance data, the same structure as the C(compliance)
            return value
          type: dict
        shells:
          description: >-
            The same structure as the C(shells) return value
          type: dict
    o0_paths:
      description: The same structure as the C(paths) return value
      type: dict
    o0_missing:
      description: What the host was asked for and did not have
      type: dict
      contains:
        commands:
          description: >-
            The same list as the C(missing_commands) return value
          type: list
          elements: str
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
          description: >-
            What was asked and what answered - C(getconf) maps the
            variable probed to the value it printed
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
          description: >-
            Whether XCU is supported. Can be true, false, or "partial"
            when a required utility is missing.
          type: raw
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
          description: >-
            What was asked and what answered. C(getconf) maps each
            variable probed to the value it printed, null where the
            variable was probed and the platform would not answer.
            C(missing) appears beside it only when a required utility
            was not found, and names the ones that were not.
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
          description: >-
            Whether XSI is supported. Can be true, false, or "partial"
            when a required utility is missing.
          type: raw
          sample: true
        version:
          description: Version information (when supported)
          type: dict
          contains:
            issue:
              description: >-
                X/Open Issue number, the C(_XOPEN_VERSION) getconf
                printed divided by one hundred
              type: int
              sample: 7
            pretty:
              description: Human-readable issue string
              type: str
              sample: "Issue 7"
        canaries:
          description: >-
            What was asked and what answered. C(getconf) maps each
            variable probed to the value it printed, null where the
            variable was probed and the platform would not answer.
            C(missing) appears beside it only when a required utility
            was not found, and stands alone naming C(getconf) itself
            when the host has no C(getconf) to ask.
          type: dict
          sample:
            getconf:
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
          description: >-
            Whether SUS is supported. Can be true, false, or "partial"
            when XSI is supported but POSIX is not fully.
          type: raw
          sample: true
        version:
          description: >-
            Version information, returned only when both POSIX and XSI
            are fully supported and XSI named an issue
          returned: when SUS is fully supported
          type: dict
          contains:
            issue:
              description: The X/Open Issue number this version derives from
              type: int
              sample: 7
            id:
              description: SUS version number, the XSI issue less three
              type: int
              sample: 4
            pretty:
              description: Human-readable version string
              type: str
              sample: "v4"
shells:
  description: >-
    What the host's C(/bin/sh) is, keyed by its path. Describes the one
    shell the probes ran in, not the login shells C(/etc/shells) names -
    M(o0_o.posix.users) and M(o0_o.posix.facts) answer that under
    C(o0_shells).
  returned: always
  type: dict
  contains:
    aliases:
      description: >-
        The aliases the shell reported, mapping the alias name to what
        it expands to
      type: dict
      sample:
        ls: ls --color=auto
    builtins:
      description: >-
        The probed commands the shell answers itself rather than by
        running a file, sorted
      type: list
      elements: str
      sample:
        - "["
        - command
        - test
  sample:
    /bin/sh:
      aliases: {}
      builtins:
        - "["
        - command
        - test
paths:
  description: >-
    The paths the probed commands resolve to, keyed by path. Each value
    is an empty dict, left as room for metadata another producer may
    fill.
  returned: always
  type: dict
  sample:
    /bin/cat: {}
    /usr/bin/grep: {}
    /bin/sh: {}
missing_commands:
  description: >-
    The probed commands C(command -v) could not find, sorted. Names
    C(command) alone when C(command) itself is missing, since no other
    lookup can be trusted then.
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
