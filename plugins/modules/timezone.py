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
module: timezone
short_description: Detect the system timezone (IANA name) on POSIX hosts
version_added: "1.4.0"
description:
  - Detects the system timezone on POSIX systems using portable methods.
  - Works across Linux distributions, macOS, FreeBSD, and OpenBSD.
  - Attempts multiple strategies including C(/etc/timezone), the
    C(/etc/localtime) symlink target, macOS C(systemsetup -gettimezone), and
    systemd C(timedatectl) where available.
  - Falls back to returning the timezone abbreviation from C(date +%Z) when a
    full IANA timezone cannot be determined.
options: {}
author:
  - oØ.o (@o0-o)
notes:
  - This module is implemented as an action plugin and supports raw fallback.
seealso:
  - name: o0_o.posix.facts
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
      description: IANA timezone name (Region/City) when available
      type: str
      returned: when determinable
      sample: America/Los_Angeles
    abbr:
      description: Timezone abbreviation when IANA name is unavailable
      type: str
      returned: when fallback used
      sample: PDT
    config:
      description: Detection configuration details
      type: dict
      returned: always
      contains:
        path:
          description: Path of configuration file used (if applicable)
          type: str
          returned: when detected from filesystem
          sample: /etc/localtime
        command:
          description: Command used to determine timezone (if applicable)
          type: str
          returned: when detected via command
          sample: systemsetup -gettimezone
"""
