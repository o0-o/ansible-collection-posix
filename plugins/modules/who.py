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
module: who
short_description: Gather active session information using who
version_added: "1.6.0"
description:
  - Collects session details reported by the POSIX C(who) command using
    the accompanying action plugin.
notes:
  - This module must be executed via its action plugin.
author:
  - oØ.o (@o0-o)
"""

EXAMPLES = r"""
- name: Gather session information
  o0_o.posix.who:
"""

RETURN = r"""
sessions:
  description: Parsed session information.
  returned: always
  type: list
  elements: dict
"""

from ansible.module_utils.basic import AnsibleModule


def main() -> None:
    """Prevent direct execution without the action plugin."""
    module = AnsibleModule(argument_spec={}, supports_check_mode=True)
    module.fail_json(msg="This module must be run via its action plugin.")


if __name__ == "__main__":
    main()
