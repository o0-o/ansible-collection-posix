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
module: timezone
short_description: Detect the system-level timezone
version_added: "1.5.0"
description:
  - Detects the effective timezone by running C(date "+%Z %z").
  - Returns the timezone abbreviation and UTC offset.
  - Reflects the effective timezone for the user running the
    command, including any C(TZ) override.
  - Does not require Python on the target host.
options: {}
author:
  - oØ.o (@o0-o)
notes:
  - This module is implemented as an action plugin and supports
    raw fallback.
  - The raw C(TZ) environment variable is also available via the
    C(o0_o.posix.env) module or the C(environment) facts subset.
attributes:
  check_mode:
    description: >-
      This module supports check mode. Timezone detection is
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
  - module: o0_o.posix.env
    description: Collect environment variables
"""

EXAMPLES = r"""
- name: Get system timezone
  o0_o.posix.timezone:
  register: tz_reg

- name: Show timezone
  ansible.builtin.debug:
    var: tz_reg['timezone']

- name: Show abbreviation and offset
  ansible.builtin.debug:
    msg: >-
      {{ tz_reg['timezone']['abbreviation'] }}
      ({{ tz_reg['timezone']['offset'] }})
"""

RETURN = r"""
timezone:
  description: System-level timezone information
  returned: always
  type: dict
  contains:
    abbreviation:
      description: Timezone abbreviation (e.g. EST, UTC, PDT)
      type: str
      returned: always
      sample: EST
    offset:
      description: UTC offset in +/-HHMM format
      type: str
      returned: when available
      sample: "-0500"
changed:
  description: Always false as this is a read-only module
  returned: always
  type: bool
  sample: false
"""

from ansible.module_utils.basic import AnsibleModule


def main() -> None:
    """Fail if this module is run directly without the action plugin."""

    module = AnsibleModule(argument_spec={}, supports_check_mode=True)
    module.fail_json(msg="This module must be run via its action plugin.")


if __name__ == "__main__":
    main()
