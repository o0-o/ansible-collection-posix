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

__metaclass__ = type

DOCUMENTATION = r"""
---
module: which
short_description: Resolve a command's full path on POSIX systems
version_added: "1.4.0"
description:
  - Resolves the full path to a command by clearing aliases and using
    C(command -v) with a fallback to C(which).
  - Always executes in a POSIX shell to guarantee alias removal.
options:
  name:
    description:
      - The command name to resolve (e.g. C(ls), C(date)).
    type: str
    required: true
author:
  - oØ.o (@o0-o)
notes:
  - This module is implemented as an action plugin and supports raw fallback.
"""

EXAMPLES = r"""
- name: Find the path to date
  o0_o.posix.which:
    name: date
  register: date_path

- name: Show
  ansible.builtin.debug:
    var: date_path.which.path
"""

RETURN = r"""
which:
  description: Result of command resolution
  returned: always
  type: dict
  contains:
    found:
      description: Whether the command was found in PATH
      type: bool
      sample: true
    path:
      description: Full path to the command if found
      type: str
      returned: when found is true
      sample: /bin/date
"""
from ansible.module_utils.basic import AnsibleModule


def main() -> None:
    """Fail if this module is run directly without the action plugin."""

    argument_spec = {"name": {"type": "str", "required": True}}

    module = AnsibleModule(
        argument_spec=argument_spec, supports_check_mode=True
    )
    module.fail_json(msg="This module must be run via its action plugin.")


if __name__ == "__main__":
    main()
