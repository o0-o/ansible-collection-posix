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

from typing import Any, Union

from ansible.errors import AnsibleFilterError
from ansible.module_utils.common.text.converters import to_native
from ansible_collections.o0_o.posix.plugins.module_utils.uname_utils import (
    _parse_uname,
)

DOCUMENTATION = r"""
---
name: uname
short_description: Parse uname command output
version_added: "1.4.0"
description:
  - Parse output from the uname command into structured data using jc
  - Returns normalized structure with kernel, architecture, and hostname
    information
options:
  _input:
    description:
      - Command output from 'uname -a' as string, list of lines, or
        command result dict
    type: raw
    required: true
requirements:
  - jc (Python library)
  - dnspython (Python library - required for hostname parsing)
  - idna (Python library - required for hostname parsing)
  - tldextract (Python library - required for hostname parsing)
notes:
  - Requires uname to be run with -a flag for complete parsing
  - The jc library will raise an error if output is incomplete
  - Hostname information includes short and long (FQDN) forms when available
author:
  - oØ.o (@o0-o)
"""

EXAMPLES = r"""
# Parse uname -a output
- name: Get system information
  ansible.builtin.command:
    cmd: uname -a
  register: uname_result

- name: Parse uname output
  ansible.builtin.debug:
    msg: "{{ uname_result.stdout | o0_o.posix.uname }}"

- name: Display kernel name
  ansible.builtin.debug:
    msg: "System: {{ uname_result.stdout | o0_o.posix.uname }}"
"""

RETURN = r"""
kernel:
  description: Kernel information
  type: dict
  returned: always
  contains:
    pretty:
      description: Original kernel name
      type: str
      sample: Linux
    name:
      description: Normalized kernel name (lowercase)
      type: str
      sample: linux
    version:
      description: Version information
      type: dict
      contains:
        id:
          description: Kernel release version
          type: str
          sample: 5.15.0-91-generic
architecture:
  description: System architecture
  type: str
  returned: always
  sample: x86_64
hostname:
  description: Hostname information
  type: dict
  returned: when node_name is present
  contains:
    short:
      description: Short hostname (first label)
      type: str
      sample: webserver
    long:
      description: Fully qualified domain name
      type: str
      returned: when FQDN is available
      sample: webserver.example.com
"""


class FilterModule:
    """Filter for parsing uname command output."""

    def filters(self) -> dict[str, Any]:
        """Return the filter functions."""
        return {
            "uname": self.uname_filter,
        }

    def uname_filter(
        self,
        config: Union[str, list[str], dict[str, Any]],
    ) -> dict[str, Any]:
        """Parse uname output into structured data.

        Parses uname -a command output into normalized structure with:
        - kernel: dict with name, pretty, and version fields
        - architecture: system architecture string
        - hostname: dict with short and optionally long (FQDN)

        :param config: Command output from 'uname -a' as string or dict
        :returns: Normalized uname data structure
        :raises AnsibleFilterError: If parsing fails
        """
        if isinstance(config, list):
            config = "\n".join(config)
        elif isinstance(config, dict):
            config = config.get("stdout") or ""

        parsed, errors = _parse_uname(str(config), "")
        if parsed is not None:
            return parsed
        msg = to_native(errors[0]) if errors else "unknown error"
        raise AnsibleFilterError(f"uname failed: {msg}")
