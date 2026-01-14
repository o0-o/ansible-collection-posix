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
module: facts
short_description: Gather POSIX facts from the managed host
version_added: '1.3.0'
description:
  - Collects comprehensive POSIX facts from remote hosts.
  - Gathers system information including kernel, mounts, users, locale,
    timezone, and compliance data.
  - Uses efficient shell commands and file reads where possible.
  - Does not require Python on the managed host.
options:
  gather_subset:
    description:
      - List of fact subsets to gather.
      - Use C(all) to gather all available facts.
      - Use C(min) for minimal facts (uname only).
      - Use C(!subset) to exclude specific subsets.
    type: list
    elements: str
    default: [all]
    choices:
      - all
      - min
      - uname
      - compliance
      - mounts
      - fstab
      - users
      - locale
      - timezone
      - '!all'
      - '!uname'
      - '!compliance'
      - '!mounts'
      - '!fstab'
      - '!users'
      - '!locale'
      - '!timezone'
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

- name: Gather minimal facts (uname, locale, timezone, compliance)
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

- name: Use gathered facts with is posix test
  o0_o.posix.facts:
  register: posix_facts

- name: Display compliance status
  ansible.builtin.debug:
    msg: "System is POSIX: {{ ansible_facts is posix }}"
  when: ansible_facts is defined
"""

RETURN = r"""
ansible_facts:
  description: Dictionary of gathered POSIX facts.
  returned: always
  type: dict
  contains:
    o0_os:
      description: Operating system facts.
      type: dict
      returned: always
      contains:
        kernel:
          description: Kernel information from uname.
          type: dict
          returned: when uname subset is gathered
          sample:
            name: "linux"
            pretty: "Linux"
            version:
              id: "6.1.0-17-amd64"
        time:
          description: Current time and timezone information.
          type: dict
          returned: when timezone subset is gathered
          contains:
            epoch:
              description: Unix timestamp
              type: int
              sample: 1234567890
            pretty:
              description: Human-readable datetime
              type: str
              sample: "2025-01-15 10:30:00 UTC"
            zone:
              description: Timezone details
              type: dict
              contains:
                name:
                  description: Timezone name abbreviation
                  type: str
                  sample: "UTC"
                offset:
                  description: Timezone offset
                  type: str
                  sample: "+0000"
                config:
                  description: Timezone configuration files
                  type: dict
                  contains:
                    '/etc/localtime':
                      description: Timezone file information
                      type: dict
                      contains:
                        type:
                          description: File type
                          type: str
                          sample: "link"
                        links:
                          description: Symlink target paths
                          type: list
                          elements: str
                          returned: when type is link
                          sample: ["/usr/share/zoneinfo/UTC"]
        locale:
          description: System locale information.
          type: dict
          returned: when locale subset is gathered
          sample:
            language: "en_US.UTF-8"
            all: "en_US.UTF-8"
        users:
          description: User accounts from /etc/passwd.
          type: dict
          returned: when users subset is gathered
        groups:
          description: Groups from /etc/group.
          type: dict
          returned: when users subset is gathered
        shells:
          description: Login shells listed in C(/etc/shells).
          type: list
          elements: str
          returned: when users subset is gathered
        compliance:
          description: Standards compliance information.
          type: dict
          returned: when compliance subset is gathered
          sample:
            posix:
              components:
                xsh:
                  version:
                    name: "POSIX.1-2008"
    o0_storage:
      description: Storage and filesystem facts.
      type: dict
      returned: when storage subsets are gathered
      contains:
        mounts:
          description: Current mount points.
          type: list
          returned: when mounts subset is gathered
          sample:
            - source: "/dev/sda1"
              mount: "/"
              type: "ext4"
              options: ["rw", "relatime"]
        config:
          description: Storage configuration files.
          type: dict
          contains:
            '/etc/fstab':
              description: Parsed fstab entries.
              type: list
              returned: when fstab subset is gathered
    o0_network:
      description: Network facts.
      type: dict
      returned: when uname subset is gathered
      contains:
        hostname:
          description: System hostname from uname.
          type: dict
          sample:
            short: "server01"
            long: "server01.example.com"
    o0_hardware:
      description: Hardware facts from dmidecode.
      type: dict
      returned: when hardware subset is gathered
      contains:
        baseboard:
          description: Baseboard/motherboard information.
          type: dict
          contains:
            architecture:
              description: CPU architecture (merged from uname)
              type: str
              sample: "x86_64"
            make:
              description: Manufacturer
              type: str
            model:
              description: Model name
              type: str
        processors:
          description: Processor information.
          type: dict
        memory:
          description: Memory module information.
          type: dict
        chassis:
          description: Chassis information.
          type: dict
        power:
          description: Power supply information.
          type: dict
"""

from ansible.module_utils.basic import AnsibleModule


def main():
    """Fail if this module is run directly without the action plugin."""
    argument_spec = {
        "gather_subset": {
            "type": "list",
            "elements": "str",
            "default": ["all"],
            "choices": [
                "all",
                "min",
                "uname",
                "compliance",
                "mounts",
                "fstab",
                "users",
                "locale",
                "timezone",
                "!all",
                "!uname",
                "!compliance",
                "!mounts",
                "!fstab",
                "!users",
                "!locale",
                "!timezone",
            ],
        }
    }

    module = AnsibleModule(
        argument_spec=argument_spec, supports_check_mode=True
    )

    module.fail_json(msg="This module must be run via its action plugin.")


if __name__ == "__main__":
    main()
