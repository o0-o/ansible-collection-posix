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
module: uname
short_description: Gather kernel, hostname, and architecture facts
version_added: "1.5.0"
description:
  - Runs C(uname -a) on the target and parses the output into
    structured kernel, hostname, and architecture data.
  - Uses jc for primary parsing with a manual fallback for
    platforms jc cannot handle (e.g. OpenBSD).
  - Does not require Python on the target host.
options: {}
author:
  - oØ.o (@o0-o)
notes:
  - This module is implemented as an action plugin and supports
    raw fallback.
attributes:
  check_mode:
    description: >-
      This module supports check mode. The uname command is
      read-only so behavior is identical.
    support: full
  async:
    description: This module does not support async operation.
    support: none
  platform:
    description: Only POSIX platforms are supported.
    support: full
    platforms: posix
seealso:
  - module: o0_o.posix.facts
    description: Gather comprehensive POSIX facts
  - module: o0_o.posix.compliance
    description: Check POSIX compliance
"""

EXAMPLES = r"""
- name: Gather uname facts
  o0_o.posix.uname:
  register: uname_reg

- name: Show kernel name
  ansible.builtin.debug:
    var: uname_reg['uname']['kernel']['name']

- name: Show hostname
  ansible.builtin.debug:
    var: uname_reg['uname']['hostname']

- name: Show architecture
  ansible.builtin.debug:
    var: uname_reg['uname']['architecture']
"""

RETURN = r"""
uname:
  description: Parsed uname data
  returned: always
  type: dict
  contains:
    kernel:
      description: Kernel information
      type: dict
      contains:
        name:
          description: Normalized kernel name (lowercase)
          type: str
          sample: linux
        pretty:
          description: Original kernel name
          type: str
          sample: Linux
        version:
          description: Kernel version information
          type: dict
          contains:
            id:
              description: Kernel release version
              type: str
              sample: "5.15.0-91-generic"
    hostname:
      description: System hostname
      type: dict
      returned: when node_name is present
      contains:
        short:
          description: Short hostname
          type: str
          sample: webserver
        long:
          description: Fully qualified domain name
          type: str
          returned: when FQDN is available
          sample: webserver.example.com
    architecture:
      description: System architecture
      type: str
      returned: when machine field is present
      sample: x86_64
changed:
  description: Always false as this is a read-only module
  returned: always
  type: bool
  sample: false
msg:
  description: Summary message
  returned: always
  type: str
  sample: "Gathered uname facts"
"""

from ansible.module_utils.basic import AnsibleModule


def main() -> None:
    """Fail if this module is run directly without the action plugin."""

    module = AnsibleModule(argument_spec={}, supports_check_mode=True)
    module.fail_json(msg="This module must be run via its action plugin.")


if __name__ == "__main__":
    main()
