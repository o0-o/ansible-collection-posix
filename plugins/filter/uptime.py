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

"""Filter exposing the uptime parser."""

from __future__ import annotations

from typing import Any, Dict

from ansible.errors import AnsibleFilterError
from ansible.module_utils.common.text.converters import to_native

from ansible_collections.o0_o.posix.plugins.module_utils import parse_uptime

DOCUMENTATION = r"""
---
name: uptime
short_description: Parse uptime command output
version_added: "1.6.0"
description:
  - Parse the output of the POSIX C(uptime) command into structured data.
  - Returns elapsed uptime (seconds, ISO 8601, pretty) and load averages.
  - Supports both GNU/Linux and BSD style uptime formatting.
options:
  _input:
    description:
      - Raw uptime output as string, list of lines, or command result dict.
    type: raw
    required: true
author:
  - oØ.o (@o0-o)
"""

EXAMPLES = r"""
# Parse uptime output from command module
- name: Gather uptime
  ansible.builtin.command:
    cmd: uptime
  register: uptime_result

- name: Parse uptime
  ansible.builtin.set_fact:
    uptime_info: "{{ uptime_result | o0_o.posix.uptime }}"

- name: Show load average
  ansible.builtin.debug:
    msg: "1 minute load {{ uptime_info.load['1'] }}"
"""

RETURN = r"""
_value:
  description: Parsed uptime data.
  type: dict
  returned: always
  contains:
    uptime:
      description: Uptime details.
      type: dict
      contains:
        elapsed:
          description: Parsed elapsed runtime (seconds, iso, pretty).
          type: dict
        started:
          description: Estimated start time derived from elapsed runtime.
          type: dict
    login_sessions:
      description: Number of logged-in sessions reported by uptime.
      type: int
    load:
      description: Load averages.
      type: dict
      contains:
        '1m':
          description: One-minute load average.
          type: float
        '5m':
          description: Five-minute load average.
          type: float
        '15m':
          description: Fifteen-minute load average.
          type: float
"""


class FilterModule:
    """Uptime parsing filter."""

    def filters(self) -> Dict[str, Any]:
        return {"uptime": self.uptime_filter}

    def uptime_filter(self, value: Any) -> Dict[str, Any]:
        """Parse uptime command output into structured data."""
        try:
            return parse_uptime(value)
        except Exception as exc:  # pragma: no cover - defensive
            raise AnsibleFilterError(
                f"uptime failed: {type(exc).__name__}: {to_native(exc)}"
            ) from exc
