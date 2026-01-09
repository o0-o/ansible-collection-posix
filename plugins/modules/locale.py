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
module: locale
short_description: Detect the system locale on POSIX hosts
version_added: "1.4.0"
description:
  - Detects the system locale categories on POSIX hosts.
  - Reads locale values from the process environment and the
    C(locale) command output.
options: {}
author:
  - oØ.o (@o0-o)
notes:
  - This module is implemented as an action plugin and supports raw fallback.
seealso:
  - module: o0_o.posix.timezone
    description: Detect the system timezone
"""

EXAMPLES = r"""
- name: Get locale
  o0_o.posix.locale:
  register: lc

- name: Show locale
  ansible.builtin.debug:
    var: lc.locale
"""

RETURN = r"""
locale:
  description: Detected locale categories
  returned: always
  type: dict
  contains:
    language:
      description: Value of LANG
      type: str
      returned: when available
      sample: en_US.UTF-8
    all:
      description: Value of LC_ALL
      type: str
      returned: when available
      sample: en_US.UTF-8
    characters:
      description: Value of LC_CTYPE
      type: str
      returned: when available
      sample: en_US.UTF-8
    collation:
      description: Value of LC_COLLATE
      type: str
      returned: when available
      sample: en_US.UTF-8
    messages:
      description: Value of LC_MESSAGES
      type: str
      returned: when available
      sample: en_US.UTF-8
    monetary:
      description: Value of LC_MONETARY
      type: str
      returned: when available
      sample: en_US.UTF-8
    numeric:
      description: Value of LC_NUMERIC
      type: str
      returned: when available
      sample: en_US.UTF-8
    time:
      description: Value of LC_TIME
      type: str
      returned: when available
      sample: en_US.UTF-8
"""

from ansible.module_utils.basic import AnsibleModule


def main() -> None:
    """Fail if this module is run directly without the action plugin."""

    module = AnsibleModule(argument_spec={}, supports_check_mode=True)
    module.fail_json(msg="This module must be run via its action plugin.")


if __name__ == "__main__":
    main()
