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
      - When true, also publishes what this module observed as facts -
        C(o0_os.compliance) and C(o0_paths).
      - This allows the compliance data to be used by subsequent tasks via
        ansible_facts without needing to register the result.
      - The facts are the same values this module returns, under the
        names M(o0_o.posix.facts) publishes them by, because both
        producers share the processor that names them. The
        C(missing_commands) return is the one value derived rather
        than published - it reads back out of the C(missing) lists the
        standards already record it in.
    type: bool
    default: false
    version_added: "2.0.0"
extends_documentation_fragment:
  - o0_o.posix.evidence
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
    The facts published when C(gather=true) - what this module
    observed, under the names the shared processor gives them.
    Nothing here is un-prefixed.
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
            return value, which already carries C(sh_posix_compliant)
            and the C(evidence) for it
          type: dict
    o0_paths:
      description: The same structure as the C(paths) return value
      type: dict
compliance:
  description: >-
    Dictionary of compliance standards detected. Contains top-level keys for
    each standard (xsh, xcu, xsi, posix, sus) with their support status,
    the behavioral C(sh_posix_compliant) verdict, and the C(evidence)
    for that verdict.
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
        evidence:
          description:
            - What decided the answer, in the one provenance
              vocabulary this collection speaks. The C(evidence) notes
              on this module document its kinds; every standard below
              names its own in the same shape.
            - C(commands) names the probes that were consulted, by
              the name each is known by rather than by the argv it was
              run with. XSI is asked for two variables and looks for
              four utilities, and one name answers for every
              invocation of one command, because what each of them was
              asked is already in C(config) and in C(missing).
            - C(config) maps each POSIX configuration variable those
              probes read to the value the host answered with, typed
              the way C(o0_os.config) types one - an integer where the
              host printed a number - so the two join by variable name
              and find one answer. A variable the host would not
              answer is named by the command that asked for it and
              left out of C(config), which is what leaving one out
              means in C(o0_os.config) too.
            - Both kinds are always present, because both are always
              attempted. The vocabulary's third kind, C(files), is
              absent throughout the namespace, since compliance reads
              no files at all.
          type: dict
          contains:
            commands:
              description: >-
                The probes that were consulted, by the name each is
                known by
              type: list
              elements: str
              sample: ["getconf"]
            config:
              description: >-
                The configuration variables the probes read, mapped to
                the values the host answered with
              type: dict
              sample:
                _POSIX_VERSION: 200809
          sample:
            commands:
              - getconf
            config:
              _POSIX_VERSION: 200809
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
        missing:
          description: >-
            The required utilities the host did not have, sorted, and
            empty where it had them all. A finding rather than
            evidence for one - what evidences it is the lookup that
            missed, named among C(evidence.commands).
          type: list
          elements: str
          sample: []
        evidence:
          description: >-
            What decided the answer, in the shape C(xsh) names it: the
            C(getconf) probe that dated the standard, and the
            C(command) each utility C(missing) records was looked for
            with. Where the host has no
            C(_POSIX2_VERSION) to answer - POSIX.2 was merged into
            POSIX.1, so glibc does not - the probe named here is the
            C(_POSIX_VERSION) one that answered in its place.
          type: dict
          sample:
            commands:
              - getconf
            config:
              _POSIX2_VERSION: 200809
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
        missing:
          description: >-
            The required utilities the host did not have, sorted, and
            empty where it had them all. It names C(getconf) itself
            when the host has none to ask, which is also why XSI is
            the standard that can be unsupported with nothing but a
            lookup to show for it.
          type: list
          elements: str
          sample: []
        evidence:
          description: >-
            What decided the answer, in the shape C(xsh) names it. XSI
            is probed twice, so C(config) carries both the
            C(_XOPEN_UNIX) that decided support and the
            C(_XOPEN_VERSION) that dated it, while C(commands) names
            C(getconf) once for the two of them, and C(command) beside
            it wherever C(missing) records a utility.
          type: dict
          sample:
            commands:
              - getconf
            config:
              _XOPEN_UNIX: 1
              _XOPEN_VERSION: 700
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
        evidence:
          description: >-
            What decided the answer, in the shape C(xsh) names it.
            POSIX runs no probe of its own, so it names the evidence
            of the two standards it is composed of - XSH first, then
            XCU - and a consumer reads the verdict and its support
            together without having to know which standards add up to
            it.
          type: dict
          sample:
            commands:
              - getconf
            config:
              _POSIX_VERSION: 200809
              _POSIX2_VERSION: 200809
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
        evidence:
          description: >-
            What decided the answer, in the shape C(xsh) names it. SUS
            runs no probe of its own either, so it names POSIX's
            evidence and then XSI's, which is every probe the
            namespace ran bar the behavioral one.
          type: dict
    sh_posix_compliant:
      description: >-
        The one behavioral verdict in a subsystem of declarations -
        whether C(/bin/sh) actually passed a basic POSIX shell test
        rather than merely declaring a version. Absent where the probe
        did not run.
      type: bool
      sample: true
    evidence:
      description: >-
        What decided C(sh_posix_compliant), the namespace's own
        verdict, named beside it the way each standard names its own.
        A command and nothing else - the probe's answer is the
        published verdict rather than a configuration variable it
        read, so there is no C(config) here to carry it.
      type: dict
      sample:
        commands:
          - sh
paths:
  description: >-
    What the probes observed about the paths they touched, keyed by
    the canonical absolute path. A command that resolved is an entry
    at the file it resolved to; a command that did not is a C(null) -
    confirmed absent - at its name in each directory the resolutions
    show were searched; and the aliases and builtins the shell
    answered with are fields on that shell's own entry, because they
    describe the shell and not the names it was asked about.
  returned: always
  type: dict
  contains:
    executable:
      description: Whether the path is executable
      type: bool
    executable_evidence:
      description: >-
        How C(executable) was arrived at - C(inferred) from a command
        resolution here, C(probed) where a producer read a permission
      type: str
      sample: inferred
    aliases:
      description: >-
        For the shell that answered the probes, the aliases it
        reported, mapping the alias name to what it expands to
      type: dict
      sample:
        ls: ls --color=auto
    builtins:
      description: >-
        For the shell that answered the probes, the probed commands it
        answers itself rather than by running a file, sorted
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
    /usr/bin/grep:
      executable: true
      executable_evidence: inferred
    /usr/bin/pax: null
missing_commands:
  description: >-
    The probed commands C(command -v) could not find, sorted, derived
    from the C(missing) list each standard records its own misses in.
    Names C(command) alone when C(command) itself is missing, since no
    other lookup can be trusted then.
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
