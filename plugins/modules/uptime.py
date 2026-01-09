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
module: uptime
short_description: Gather POSIX uptime information
version_added: "1.6.0"
description:
  - Collects uptime details (elapsed runtime, start time, logged-in
    sessions, load averages) by invoking the POSIX C(uptime) command.
  - Implemented as an action plugin with raw fallback support.
notes:
  - This module must be executed via its action plugin.
author:
  - oØ.o (@o0-o)
"""

EXAMPLES = r"""
- name: Gather uptime details
  o0_o.posix.uptime:
"""

RETURN = r"""
uptime:
  description: Structured uptime information.
  returned: always
  type: dict
  contains:
    elapsed:
      description: Elapsed runtime with seconds/pretty/ISO representation.
      type: dict
    started:
      description: Estimated start time parsed into structured datetime
        fields.
      type: dict
login_sessions:
  description: Number of logged-in sessions reported by uptime.
  returned: always
  type: int
load:
  description: Load averages from the uptime output.
  returned: always
  type: dict
  contains:
    '1':
      description: One minute load average.
      type: float
    '5':
      description: Five minute load average.
      type: float
    '15':
      description: Fifteen minute load average.
      type: float
"""

from ansible.module_utils.basic import AnsibleModule


def main() -> None:
    """Prevent direct execution without the action plugin."""
    module = AnsibleModule(argument_spec={}, supports_check_mode=True)
    module.fail_json(msg="This module must be run via its action plugin.")


if __name__ == "__main__":
    main()
