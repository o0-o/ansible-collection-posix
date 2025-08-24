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

from typing import Any, Dict, List, Union

from ansible_collections.o0_o.posix.plugins.filter_utils import JCBase

try:
    from ansible_collections.o0_o.utils.plugins.filter import HostnameFilter

    HAS_HOSTNAME_FILTER = True
except ImportError:
    HAS_HOSTNAME_FILTER = False

DOCUMENTATION = r"""
---
name: uname
short_description: Parse uname command output
version_added: "1.1.0"
description:
  - Parse output from the uname command into structured data using jc
  - Can return either raw jc format or simplified facts structure
  - When used with facts=True, returns kernel, architecture, and
    hostname information
options:
  _input:
    description:
      - Command output from 'uname -a' as string, list of lines, or
        command result dict
    type: raw
    required: true
  facts:
    description:
      - If True, format output for direct merge into Ansible facts
      - Returns simplified structure with kernel, architecture, and
        hostname keys
    type: bool
    default: false
requirements:
  - jc (Python library)
  - dnspython (Python library - required for hostname parsing when facts=True)
  - idna (Python library - required for hostname parsing when facts=True)
  - tldextract (Python library - required for hostname parsing when facts=True)
notes:
  - Requires uname to be run with -a flag for complete parsing
  - The jc library will raise an error if output is incomplete
  - When facts=True, hostname information includes short and long (FQDN) forms
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

# Use facts format for simplified structure
- name: Parse for facts
  ansible.builtin.set_fact:
    system_info: "{{ uname_result.stdout | o0_o.posix.uname(facts=true) }}"

- name: Display kernel name
  ansible.builtin.debug:
    msg: "Running {{ system_info.kernel.name }} kernel"
"""

RETURN = r"""
# When facts=False (default)
kernel_name:
  description: Operating system kernel name
  type: str
  returned: always
  sample: Linux
node_name:
  description: Network node hostname
  type: str
  returned: always
  sample: webserver.example.com
kernel_release:
  description: Kernel release version
  type: str
  returned: always
  sample: 5.15.0-91-generic
kernel_version:
  description: Kernel version details
  type: str
  returned: when available
  sample: "#101-Ubuntu SMP Tue Nov 14 13:30:08 UTC 2023"
machine:
  description: Machine hardware name
  type: str
  returned: always
  sample: x86_64

# When facts=True
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


class FilterModule(JCBase):
    """Filter for parsing uname command output using jc."""

    def filters(self) -> Dict[str, Any]:
        """Return the filter functions."""
        return {
            "uname": self.uname,
        }

    def _format_as_facts(self, parsed: Dict[str, Any]) -> Dict[str, Any]:
        """Format parsed uname data for Ansible facts structure.

        Converts jc's raw uname parsing into a simplified facts
        structure suitable for direct merge into Ansible facts, with
        kernel, architecture, and hostname information.

        :param parsed: Parsed uname data from jc
        :returns: Facts structure with kernel, arch, hostname
        """
        facts_data = {}

        # Kernel information
        if "kernel_name" in parsed:
            kernel = {
                "pretty": parsed["kernel_name"],
                "name": parsed["kernel_name"].lower().replace(" ", "_"),
            }
            if "kernel_release" in parsed:
                kernel["version"] = {"id": parsed["kernel_release"]}
            facts_data["kernel"] = kernel

        # Architecture
        if "machine" in parsed:
            facts_data["architecture"] = parsed["machine"]
        elif "processor" in parsed and parsed["processor"] != "unknown":
            facts_data["architecture"] = parsed["processor"]
        elif (
            "hardware_platform" in parsed
            and parsed["hardware_platform"] != "unknown"
        ):
            facts_data["architecture"] = parsed["hardware_platform"]

        # Hostname - use short and long (if present)
        if "node_name" in parsed:
            hostname_filter = HostnameFilter()
            hostname_data = hostname_filter.hostname(parsed["node_name"])

            # Always include short
            hostname_facts = {"short": hostname_data.get("short", "")}

            # Include long only if it's present (FQDN)
            if "long" in hostname_data:
                hostname_facts["long"] = hostname_data["long"]

            facts_data["hostname"] = hostname_facts

        return facts_data

    def uname(
        self,
        data: Union[str, List[str], Dict[str, Any]],
        facts: bool = False,
    ) -> Dict[str, Any]:
        """Parse uname output into structured data using jc.

        .. note::
            Requires uname to be run with -a flag for complete parsing.
            jc will raise an error if output is incomplete.

        :param data: Command output from 'uname -a'
        :param facts: If True, format for direct merge into Ansible
            facts
        :returns: Parsed uname data, or facts structure with kernel,
            arch, hostname
        """
        # Get parsed data from jc
        parsed = self.parse_command(data, "uname")

        if not facts:
            # Return jc's parsed format directly
            return parsed

        # Check for hostname filter dependency when facts=True
        if not HAS_HOSTNAME_FILTER:
            raise ImportError(
                "The 'facts' mode requires the o0_o.utils collection. "
                "Please install it with: "
                "ansible-galaxy collection install o0_o.utils"
            )

        # Format for facts module using separate method
        return self._format_as_facts(parsed)
