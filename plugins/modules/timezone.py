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
short_description: Detect the system timezone details on POSIX hosts
version_added: "1.4.0"
description:
  - Detects timezone information on POSIX systems.
  - Discovers the tzdb zone when available, parses the POSIX TZ
    definition from the zoneinfo file, and captures the active
    abbreviation and offset from the C(date) command.
options: {}
author:
  - oØ.o (@o0-o)
notes:
  - This module is implemented as an action plugin and supports raw fallback.
seealso:
  - module: o0_o.posix.facts
    description: Minimal POSIX facts gathering
"""

EXAMPLES = r"""
- name: Get timezone
  o0_o.posix.timezone:
  register: tz

- name: Show timezone
  ansible.builtin.debug:
    var: tz.timezone
"""

RETURN = r"""
timezone:
  description: Detected timezone information
  returned: always
  type: dict
  contains:
    name:
      description: TZ database identifier when detected
      type: str
      returned: when available
      sample: America/New_York
    zone:
      description: Deprecated alias of C(name) retained for compatibility
      type: str
      returned: when available
    config:
      description: Mapping of examined timezone configuration files
      type: dict
      returned: when available
      sample:
        /etc/localtime:
          link: /var/db/timezone/zoneinfo/America/New_York
      contains:
        /etc/localtime:
          description: Entry for the active localtime reference
          type: dict
          contains:
            link:
              description: Symlink target or resolved zoneinfo file
              type: str
              returned: when available
              sample: /var/db/timezone/zoneinfo/America/New_York
    posix:
      description: Raw POSIX TZ string parsed from the zoneinfo file
      type: str
      returned: when available
      sample: EST5EDT,M3.2.0,M11.1.0
    standard:
      description: Standard time definition
      type: dict
      returned: when available
      contains:
        abbr:
          description: Standard time abbreviation
          type: str
          sample: EST
        offset:
          description: Standard offset formatted +/-HH:MM[:SS]
          type: str
          sample: -05:00
    daylight:
      description: Daylight saving definition when present
      type: dict
      returned: when available
      contains:
        abbr:
          description: Daylight time abbreviation
          type: str
          sample: EDT
        offset:
          description: Daylight offset formatted +/-HH:MM[:SS]
          type: str
          sample: -04:00
        start:
          description: Daylight saving start components
          type: dict
          contains:
            month:
              description: Month index (1-12)
              type: int
            week:
              description: Week number (1-4, 5=last)
              type: int
            weekday:
              description: Day of week (0=Sunday)
              type: int
            time:
              description: Transition time (HH:MM[:SS])
              type: str
        end:
          description: Daylight saving end components
          type: dict
          contains:
            month:
              description: Month index (1-12)
              type: int
            week:
              description: Week number (1-4, 5=last)
              type: int
            weekday:
              description: Day of week (0=Sunday)
              type: int
            time:
              description: Transition time (HH:MM[:SS])
              type: str
    abbr:
      description: Active timezone abbreviation from C(date +%Z)
      type: str
      returned: when available
      sample: EDT
    offset:
      description: Active numeric offset from C(date +%z)
      type: str
      returned: when available
      sample: -0400
"""
from ansible.module_utils.basic import AnsibleModule


def main() -> None:
    """Fail if this module is run directly without the action plugin."""

    module = AnsibleModule(argument_spec={}, supports_check_mode=True)
    module.fail_json(msg="This module must be run via its action plugin.")


if __name__ == "__main__":
    main()
