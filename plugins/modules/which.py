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
module: which
short_description: Resolve a command's full path on POSIX systems
version_added: "2.0.0"
description:
  - Resolves the full path to a command by clearing aliases and using
    C(command -v) with a fallback to C(which).
  - Returns command as-is for shell built-ins
  - Always executes in a POSIX shell to guarantee alias removal.
options:
  command:
    description:
      - The command to resolve (e.g. C(ls), C(date)).
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
    command: date
  register: date_path

- name: Show
  ansible.builtin.debug:
    var: date_path.path
"""

RETURN = r"""
path:
  description: Full path to the command if found
  type: str
  returned: always
  sample: /bin/date
"""
from ansible.module_utils.basic import AnsibleModule


def main() -> None:
    """Fail if this module is run directly without the action plugin."""

    argument_spec = {"command": {"type": "str", "required": True}}

    module = AnsibleModule(
        argument_spec=argument_spec, supports_check_mode=True
    )
    module.fail_json(msg="This module must be run via its action plugin.")


if __name__ == "__main__":
    main()
