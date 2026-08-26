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
module: facts
short_description: Gather POSIX facts from the managed host
version_added: '1.3.0'
description:
  - Collects comprehensive POSIX facts from remote hosts.
  - Gathers the kernel, hostname and architecture C(uname) reports, the
    host's timezone, its standards compliance, its hardware inventory,
    its mounts and C(/etc/fstab), its users and groups, and the
    environment and locale of the user the play connects as.
  - Uses efficient shell commands and file reads where possible.
  - Does not require Python on the managed host.
options:
  gather_subset:
    description:
      - List of fact subsets to gather.
      - Use C(all) to gather every subset.
      - Use C(min) for the subsets that cost one round trip and no
        privilege - C(uname), C(environment), C(timezone) and
        C(compliance).
      - Use C(storage) for C(mounts) and C(fstab) together.
      - Use C(!subset) to exclude a subset, or C(!group) to exclude
        every subset a group names.
    type: list
    elements: str
    default: [all]
    choices:
      - all
      - min
      - storage
      - uname
      - compliance
      - timezone
      - dmidecode
      - mounts
      - fstab
      - users
      - environment
      - '!all'
      - '!min'
      - '!storage'
      - '!uname'
      - '!compliance'
      - '!timezone'
      - '!dmidecode'
      - '!mounts'
      - '!fstab'
      - '!users'
      - '!environment'
author:
  - oØ.o (@o0-o)
seealso:
  - module: ansible.builtin.setup
notes:
  - This module must be run via its action plugin.
  - It is designed to support bootstrapping environments where Python
    may not be available on the managed node.
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
- name: Gather all POSIX facts
  o0_o.posix.facts:

- name: Gather minimal facts (uname, environment, timezone, compliance)
  o0_o.posix.facts:
    gather_subset:
      - min

- name: Gather only system info and mounts
  o0_o.posix.facts:
    gather_subset:
      - uname
      - mounts

- name: Gather all except users
  o0_o.posix.facts:
    gather_subset:
      - all
      - '!users'

- name: Gather all except the storage subsets
  o0_o.posix.facts:
    gather_subset:
      - all
      - '!storage'

- name: Read a user's shell against the login shells the host names
  ansible.builtin.debug:
    msg: >-
      {{ ansible_facts.o0_users['0'].shell }} is a login shell:
      {{ ansible_facts.o0_users['0'].shell in ansible_facts.o0_shells }}

- name: Display compliance status
  ansible.builtin.debug:
    msg: >-
      System is POSIX:
      {{ ansible_facts.o0_os.compliance.posix.supported }}
  when: ansible_facts.o0_os.compliance is defined

- name: Run a task only where the shell utilities are fully POSIX
  o0_o.posix.command:
    argv: [grep, -E, "pattern", /etc/passwd]
  when: ansible_facts.o0_os.compliance.xcu.supported is true
"""

RETURN = r"""
ansible_facts:
  description: >-
    The facts the selected subsets answered with. Every namespace
    takes the C(o0_) prefix, and a subset that could not be gathered
    leaves its namespace absent rather than present and empty.
  returned: always
  type: dict
  contains:
    o0_os:
      description: Facts about the operating system.
      returned: >-
        when the uname, timezone or compliance subset is gathered
      type: dict
      contains:
        kernel:
          description: The kernel C(uname -a) reported.
          returned: when the uname subset is gathered
          type: dict
          contains:
            name:
              description: >-
                Kernel name, lowercased with spaces replaced by
                underscores
              type: str
              sample: linux
            pretty:
              description: Kernel name as C(uname) printed it
              type: str
              sample: Linux
            version:
              description: Kernel release
              returned: when uname reported a release
              type: dict
              contains:
                id:
                  description: Release string
                  type: str
                  sample: 6.1.0-17-amd64
        timezone:
          description: The timezone the host reports for itself.
          returned: when the timezone subset is gathered
          type: dict
          contains:
            abbreviation:
              description: Zone abbreviation
              type: str
              sample: EDT
            offset:
              description: Offset from UTC, four digits and a sign
              type: str
              sample: "-0400"
        compliance:
          description: >-
            Standards compliance keyed by standard - C(posix), C(sus),
            C(xsh), C(xcu) and C(xsi). Each entry carries the
            standard's name, abbreviation and description, whether it
            is C(supported), the C(version) detected, and the
            C(canaries) that decided the answer. Beside the standards,
            C(sh_posix_compliant) records the one behavioral probe:
            whether C(/bin/sh) actually passed a basic POSIX shell
            test, rather than merely declaring a version.
            M(o0_o.posix.compliance) builds this fact and documents
            every field of it.
          returned: when the compliance subset is gathered
          type: dict
        shells:
          description: >-
            What the host's C(/bin/sh) is, keyed by its path - the
            C(aliases) it defines and the commands it answers as
            C(builtins) rather than as files. Read from the compliance
            probes, so it describes one shell; C(o0_shells) is the
            unrelated list of login shells C(/etc/shells) names.
          returned: when the compliance subset is gathered
          type: dict
          sample:
            /bin/sh:
              aliases: {}
              builtins:
                - '['
                - command
                - test
    o0_network:
      description: Facts about the host's names.
      returned: when the uname subset is gathered
      type: dict
      contains:
        hostname:
          description: The node name C(uname) reported.
          type: dict
          contains:
            short:
              description: The name up to the first dot
              type: str
              sample: server01
            long:
              description: The fully qualified name
              returned: when uname reported a qualified name
              type: str
              sample: server01.example.com
    o0_hardware:
      description: >-
        Facts about the machine. The architecture comes from C(uname);
        every other key comes from C(dmidecode), and a key whose value
        C(dmidecode) reported as a placeholder is omitted rather than
        published as filler. Sub-dicts are keyed by the identifier
        C(dmidecode) named, normalized.
      returned: when the uname or dmidecode subset is gathered
      type: dict
      contains:
        make:
          description: System manufacturer
          returned: when dmidecode named one
          type: str
          sample: Dell Inc.
        model:
          description: System product name
          returned: when dmidecode named one
          type: str
          sample: PowerEdge R640
        version:
          description: System version
          returned: when dmidecode named a meaningful one
          type: dict
          contains:
            id:
              description: Version string
              type: str
              sample: '02'
        serial:
          description: System serial number
          returned: when dmidecode named a meaningful one
          type: str
          sample: ABCD123
        uuid:
          description: System UUID
          returned: when dmidecode named one that is not all zeros
          type: str
          sample: 4c4c4544-0044-4210-8043-b6c04f463432
        sku:
          description: System SKU number
          returned: when dmidecode named a meaningful one
          type: str
          sample: SKU=0A9E
        family:
          description: System family
          returned: when dmidecode named a meaningful one
          type: str
          sample: PowerEdge
        baseboard:
          description: The board, its firmware, and what attaches to it.
          returned: >-
            when the uname subset is gathered, or dmidecode described
            the board or anything on it
          type: dict
          contains:
            architecture:
              description: >-
                The machine architecture C(uname) reported. The only
                key here the uname subset fills in, and the only one
                a host without C(dmidecode) still answers with.
              returned: when the uname subset is gathered
              type: str
              sample: x86_64
            make:
              description: Board manufacturer
              returned: when dmidecode named one
              type: str
            model:
              description: Board product name
              returned: when dmidecode named one
              type: str
            bios:
              description: >-
                Firmware vendor, version, and release C(date) as a
                point in time - C(seconds) and C(pretty), C(seconds)
                null when the vendor's date cannot be read. Carries
                C(languages) when the firmware named any.
              returned: when dmidecode reported firmware information
              type: dict
            memory:
              description: >-
                What the memory array as a whole is - its capacity,
                its slot count, and its error correction
              returned: >-
                when dmidecode reported a memory array or memory
                devices
              type: dict
            slots:
              description: >-
                Slots grouped by type, then keyed by designation where
                designations are unique and by index where they are not
              returned: when dmidecode reported slots
              type: dict
            sockets:
              description: Processor sockets, keyed by designation
              returned: when dmidecode reported processors
              type: dict
            interfaces:
              description: Port connectors, keyed by designator
              returned: when dmidecode reported port connectors
              type: dict
            ipmi:
              description: IPMI interface version and addressing
              returned: when dmidecode reported an IPMI device
              type: dict
            devices:
              description: Onboard devices, keyed by device name
              returned: when dmidecode reported onboard devices
              type: dict
        chassis:
          description: Chassis make, model, type and asset tag
          returned: when dmidecode reported chassis information
          type: dict
        processors:
          description: >-
            Installed processors grouped by model, each carrying the
            sockets it occupies and the caches attached to it
          returned: when dmidecode reported processors
          type: dict
        memory:
          description: >-
            Installed memory modules grouped by part number, each
            carrying the locators it occupies - the module's view of
            the same devices C(baseboard.memory) summarizes
          returned: when dmidecode reported memory devices
          type: dict
        power:
          description: >-
            Power supplies grouped by make and model, each carrying the
            locations it occupies
          returned: when dmidecode reported power supplies
          type: dict
        oem:
          description: The OEM strings the firmware carries
          returned: when dmidecode reported any
          type: list
          elements: str
        config:
          description: The system configuration options the firmware names
          returned: when dmidecode reported any
          type: list
          elements: str
        status:
          description: How the system reported its last boot
          returned: when dmidecode reported boot information
          type: str
          sample: No errors detected
    o0_storage:
      description: Facts about filesystems.
      returned: when the mounts or fstab subset is gathered
      type: dict
      contains:
        mounts:
          description: >-
            What is mounted, keyed by mount point. Composed from C(df)
            and C(mount) together, so a mount point C(df) did not
            report is not reported here either. M(o0_o.posix.mounts)
            builds the same fact under its own C(mounts) return.
          returned: >-
            when the mounts subset is gathered and both df and mount
            answered
          type: dict
          contains:
            source:
              description: >-
                What is mounted there, as C(df) named it - a C(path)
                for a device, an C(address) for a network export, a
                C(uuid) or C(label) for a named volume, a C(map) for an
                automounter, or a C(name) for a special filesystem.
                Null where the source is C(none) or C(-).
              type: dict
              sample:
                path: /dev/sda1
            type:
              description: Filesystem type, as C(mount) named it
              returned: when mount reported the mount point too
              type: str
              sample: ext4
            options:
              description: >-
                The options it was mounted with, merged into one dict
                with normalized names - C(ro) reads as
                C(writable: false), the C(atime) family collapses into
                a single C(atime) enum, and an option carrying a value
                keeps it
              returned: when mount reported the mount point too
              type: dict
              sample:
                writable: true
                atime: relative
            capacity:
              description: How much of it C(df) reported in use.
              type: dict
              contains:
                total:
                  description: Size of the filesystem
                  type: dict
                  contains:
                    bytes:
                      description: Size in bytes
                      type: int
                      sample: 10737418240
                    pretty:
                      description: Size in binary units
                      type: str
                      sample: 10.00 GiB
                used:
                  description: Space in use
                  type: dict
                  contains:
                    bytes:
                      description: Bytes in use
                      type: int
                      sample: 5368709120
                    pretty:
                      description: Space in use, in binary units
                      type: str
                      sample: 5.00 GiB
                    percent:
                      description: >-
                        Share of the filesystem in use, computed from
                        the byte counts rather than taken from C(df)
                      type: float
                      sample: 50.0
        config:
          description: The files that configure what gets mounted.
          returned: when the fstab subset is gathered and the file was read
          type: dict
          contains:
            '/etc/fstab':
              description: >-
                The entries C(/etc/fstab) names, in file order. Every
                key is present on every entry, null where the file
                omitted the field. M(o0_o.posix.mounts) returns the
                same list under C(fstab).
              type: list
              elements: dict
              contains:
                source:
                  description: >-
                    What to mount, as the file spells it - a device
                    path, or a C(UUID=) or C(LABEL=) form, unparsed
                  type: str
                  sample: UUID=abc-123
                mount:
                  description: Where to mount it, null for swap
                  type: str
                  sample: /
                type:
                  description: >-
                    Filesystem type, or the list of them where the
                    field named more than one
                  type: raw
                  sample: ext4
                options:
                  description: >-
                    Mount options in file order, one single-key dict
                    each, the value C(true) for a flag and the string
                    for an option carrying one
                  type: list
                  elements: dict
                  sample:
                    - defaults: true
                    - noatime: true
                dump:
                  description: Dump frequency, null if the file omitted it
                  type: int
                  sample: 0
                pass:
                  description: Fsck pass number, null if the file omitted it
                  type: int
                  sample: 1
    o0_users:
      description: >-
        Users keyed by stringified UID. Two subsets write here and a
        run that gathers both meets in one entry per UID: C(users)
        describes every account C(/etc/passwd) names, and
        C(environment) adds the environment and locale of the one user
        the play connects as. A gather does not read SSH keys, so no
        entry carries the C(keys) that M(o0_o.posix.users) returns -
        that cost is per user and it is not what a gather is for.
      returned: when the users or environment subset is gathered
      type: dict
      contains:
        uid:
          description: Numeric user ID, the integer the key stringifies
          type: int
          sample: 1000
        name:
          description: Username
          returned: when the users subset is gathered
          type: str
          sample: o0-o
        gid:
          description: Numeric ID of the user's primary group
          returned: when the users subset is gathered
          type: int
          sample: 20
        gecos:
          description: The comment field
          returned: when the users subset is gathered
          type: str
          sample: User Account
        home:
          description: Home directory path
          returned: when the users subset is gathered
          type: str
          sample: /home/o0-o
        shell:
          description: Login shell
          returned: when the users subset is gathered
          type: str
          sample: /bin/bash
        groups:
          description: >-
            GIDs of every group the user belongs to, primary group
            included
          returned: when the users subset is gathered
          type: list
          elements: int
          sample: [20, 101]
        environment:
          description: >-
            The environment variables IEEE Std 1003.1 names, as the
            connecting user's shell reports them, keyed by variable
            name. A variable the shell did not set is absent.
          returned: when the environment subset is gathered
          type: dict
          sample:
            HOME: /home/o0-o
            LANG: en_US.UTF-8
            PATH: /usr/bin:/bin
        locale:
          description: >-
            The locale derived from the environment - C(LC_ALL) if it
            is set, otherwise C(LANG), and C(ASCII) where neither is
            set or where the answer is C(C) or C(POSIX)
          returned: when the environment subset is gathered
          type: str
          sample: en_US.UTF-8
    o0_groups:
      description: >-
        Groups keyed by stringified GID, each with its C(name), its
        integer C(gid), and the UIDs of every C(members) entry.
        M(o0_o.posix.users) publishes the same shape under the same
        name.
      returned: when the users subset is gathered
      type: dict
      sample:
        "20":
          name: staff
          gid: 20
          members:
            - 0
            - 1000
    o0_homes:
      description: >-
        The directories users call home, keyed by path, each with the
        file metadata of the path and a C(residents) list of the UIDs
        that live there. A home two users share is one entry with two
        residents.
      returned: when the users subset is gathered
      type: dict
      sample:
        /home/o0-o:
          type: directory
          uid: 1000
          gid: 20
          tags:
            - posix
            - home
          residents:
            - 1000
    o0_shell_files:
      description: >-
        The login shells users actually hold, keyed by path, each with
        the file metadata of the shell. Distinct from C(o0_shells),
        which names what C(/etc/shells) lists whether anyone holds it
        or not.
      returned: when the users subset is gathered
      type: dict
      sample:
        /bin/sh:
          type: regular
          uid: 0
          gid: 0
          tags:
            - posix
            - shell
    o0_shells:
      description: >-
        The login shells C(/etc/shells) names, in the order it names
        them. A host without that file answers with no C(o0_shells)
        rather than an empty list, which would read as a host that
        names no login shells at all.
      returned: >-
        when the users subset is gathered and the shells file was read
      type: list
      elements: str
      sample:
        - /bin/sh
        - /bin/zsh
    o0_paths:
      description: >-
        The paths the commands the compliance probes looked for resolve
        to, keyed by path. Each value is the empty dict the probe left
        room in for metadata another producer may fill.
      returned: when the compliance subset is gathered
      type: dict
      sample:
        /bin/cat: {}
        /bin/sh: {}
        /usr/bin/grep: {}
    o0_missing:
      description: What the host was asked for and did not have.
      returned: when the compliance subset is gathered
      type: dict
      contains:
        commands:
          description: >-
            The commands the compliance probes looked for and did not
            find, sorted
          type: list
          elements: str
          sample: []
"""

from ansible.module_utils.basic import AnsibleModule


def main() -> None:
    """Fail if this module is run directly without the action plugin."""
    argument_spec = {
        "gather_subset": {
            "type": "list",
            "elements": "str",
            "default": ["all"],
            "choices": [
                "all",
                "min",
                "storage",
                "uname",
                "compliance",
                "timezone",
                "dmidecode",
                "mounts",
                "fstab",
                "users",
                "environment",
                "!all",
                "!min",
                "!storage",
                "!uname",
                "!compliance",
                "!timezone",
                "!dmidecode",
                "!mounts",
                "!fstab",
                "!users",
                "!environment",
            ],
        }
    }

    module = AnsibleModule(
        argument_spec=argument_spec, supports_check_mode=True
    )

    module.fail_json(msg="This module must be run via its action plugin.")


if __name__ == "__main__":
    main()
