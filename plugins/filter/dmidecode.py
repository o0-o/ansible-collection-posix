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
from ansible_collections.o0_o.posix.plugins.module_utils import dmidecode

DOCUMENTATION = r"""
---
name: dmidecode
short_description: Parse dmidecode command output
version_added: "1.4.0"
description:
  - Parse output from the dmidecode command into structured hardware
    information using jc
  - Produce a consolidated view of chassis, baseboard, system,
    processors, memory, power supplies, IPMI, slot layout, and related
    inventory details keyed by normalized identifiers
  - Clean placeholder strings and normalize feature data so downstream
    automation receives stable values suitable for comparisons
options:
  _input:
    description:
      - Command output from 'dmidecode' as string, list of lines, or
        command result dict
    type: raw
    required: true
requirements:
  - jc (Python library)
  - ansible_collections.o0_o.utils (required for SI unit parsing)
notes:
  - The jc library parses dmidecode output which is then transformed
    into structured data organized by physical hierarchy
  - The o0_o.utils collection provides required SI parsing helpers that
    power the capacity, speed, and voltage normalization in the return
    data
  - dmidecode typically requires root/sudo privileges on the target
    system
  - Feature strings are cleaned up (e.g., "is/are supported" removed)
  - Default values like "Default string" are excluded from output
author:
  - oØ.o (@o0-o)
"""

EXAMPLES = r"""
# Parse dmidecode output
- name: Get hardware information
  ansible.builtin.command:
    cmd: dmidecode
  become: true
  register: dmi_result

- name: Parse dmidecode output
  ansible.builtin.set_fact:
    hardware: "{{ dmi_result.stdout | o0_o.posix.dmidecode }}"

# Access system information
- name: Display system details
  ansible.builtin.debug:
    msg: >-
      Manufacturer: {{ hardware['make'] }},
      Model: {{ hardware['model'] }},
      Serial: {{ hardware['serial'] }}

# Access baseboard information
- name: Display baseboard details
  ansible.builtin.debug:
    msg: >-
      Manufacturer: {{ hardware['baseboard']['make'] }},
      Model: {{ hardware['baseboard']['model'] }},
      Serial: {{ hardware['baseboard']['serial'] }}

# Get BIOS information
- name: Display BIOS details
  ansible.builtin.debug:
    msg: >-
      BIOS Vendor: {{ hardware['baseboard']['bios']['make'] }},
      Version: {{ hardware['baseboard']['bios']['version']['id'] }},
      Release Date: {{ hardware['baseboard']['bios']['date']['pretty'] }}

# Access chassis information
- name: Display chassis details
  ansible.builtin.debug:
    msg: >-
      Type: {{ hardware['chassis']['type'] }},
      Boot State: {{ hardware['chassis']['boot'] }},
      Lock: {{ hardware['chassis']['lock'] }}

# List interface ports
- name: Show interface ports
  ansible.builtin.debug:
    msg: "Port {{ item.key }}: {{ item.value }}"
  loop: >-
    {{ hardware['baseboard']['interfaces'] | dict2items }}
  when: "'interfaces' in hardware['baseboard']"

# List expansion slots
- name: Show populated expansion slots
  ansible.builtin.debug:
    msg: "Slot {{ item['description'] }}: {{ item['type'] }}"
  loop: "{{ hardware['baseboard']['slots'] }}"
  when:
    - "'slots' in hardware['baseboard']"
    - item['populated']
"""

RETURN = r"""
_value:
  description: Structured hardware information dict
  type: dict
  returned: always
  contains:
    make:
      description: System manufacturer
      type: str
      sample: "Supermicro"
    model:
      description: System product name/model
      type: str
      sample: "SSG-6028R-E1CR24L-IN001"
    version:
      description: System version information
      type: dict
      contains:
        id:
          description: Version identifier
          type: str
          sample: "0123456789"
    serial:
      description: System serial number (excluded if meaningless)
      type: str
      sample: "S290260X7639846"
    uuid:
      description: System UUID (excluded if all zeros)
      type: str
      sample: "00000000-0000-0000-0000-0C:C4:7A:BE:E4:A4"
    sku:
      description: SKU number (excluded if meaningless)
      type: str
      sample: "SKU12345"
    family:
      description: System family (excluded if meaningless)
      type: str
      sample: "Server"
    oem:
      description: OEM-specific strings (trailing whitespace stripped)
      type: list
      elements: str
      sample:
        - "Intel Haswell/Wellsburg/Grantley"
        - "Supermicro motherboard-X10 Series"
    config:
      description: >-
        System configuration options (excluded if meaningless default
        values)
      type: list
      elements: str
      sample:
        - "J1: 1-2 Normal, 2-3 Recovery"
        - "J2: 1-2 TPM Disabled, 2-3 TPM Enabled"
    status:
      description: System boot status (excluded if meaningless)
      type: str
      sample: "No errors detected"
    power:
      description: >-
        Power supply units grouped by make + model (normalized to
        lowercase with underscores). Each PSU model contains specifications
        and a locations dict keyed by location name (preferred) or group
        number (fallback).
      type: dict
      sample:
        supermicro_pws-1k62a-1r:
          make: "SUPERMICRO"
          model: "PWS-1K62A-1R"
          capacity:
            watts: 1600
            pretty: "1.6 kW"
          type: "Switching"
          range: "Auto-switch"
          hotswap: true
          locations:
            psu1:
              group: "1"
              serial: "P1K6BCG34MB0012"
              revision: "1.1"
              status: "Present, OK"
              powered: true
            psu2:
              group: "2"
              serial: "P1K6BCG34MB0011"
              revision: "1.1"
              status: "Present, OK"
              powered: true
    memory:
      description: >-
        Memory modules grouped by part number (normalized to lowercase). Each
        module contains specifications and a locations dict keyed by slot
        identifier (also lowercase).
      type: dict
      sample:
        m386a4g40dm0-cpb:
          make: "Samsung"
          model: "M386A4G40DM0-CPB"
          bits:
            data: 64
            total: 72
          ecc: true
          capacity:
            bytes: 34359738368
            pretty: "32 GiB"
          speed:
            t/s: 2133000000
            pretty: "2.13 GT/s"
          rank: 4
          locations:
            p2-dimme1:
              serial: "405A430F"
              speed:
                t/s: 1866000000
                pretty: "1.87 GT/s"
              tag: "P2-DIMME1_AssetTag (date:15/18)"
    chassis:
      description: Chassis/enclosure information
      type: dict
      contains:
        make:
          description: Chassis manufacturer
          type: str
          sample: "Supermicro"
        type:
          description: Chassis type (excluded if meaningless)
          type: str
          sample: "Rack Mount Chassis"
        version:
          description: Chassis version information
          type: dict
          contains:
            id:
              description: Version identifier
              type: str
              sample: "0123456789"
        serial:
          description: Chassis serial number (excluded if meaningless)
          type: str
          sample: "C8260FG03A30467"
        asset_tag:
          description: Asset tag (excluded if meaningless)
          type: str
          sample: "ASSET123"
        sku:
          description: SKU number (excluded if meaningless)
          type: str
          sample: "SKU12345"
        lock:
          description: Lock presence (true/false or passthrough)
          type: raw
          sample: false
        boot:
          description: Boot-up state
          type: str
          sample: "Safe"
        psu:
          description: Power supply state
          type: str
          sample: "Safe"
        thermal:
          description: Thermal state
          type: str
          sample: "Safe"
        security:
          description: Security status (excluded if meaningless)
          type: str
          sample: "None"
        height:
          description: Height (excluded if meaningless)
          type: str
          sample: "2U"
    baseboard:
      description: Baseboard/motherboard information
      type: dict
      contains:
        make:
          description: Baseboard manufacturer
          type: str
          sample: "Supermicro"
        model:
          description: Baseboard product name/model
          type: str
          sample: "X10DSC+"
        version:
          description: Baseboard version information
          type: dict
          contains:
            id:
              description: Version identifier
              type: str
              sample: "1.01"
        serial:
          description: Baseboard serial number (excluded if meaningless)
          type: str
          sample: "HM174S001623"
        asset_tag:
          description: Asset tag (excluded if meaningless)
          type: str
          sample: "ASSET123"
        location:
          description: Location in chassis (excluded if meaningless)
          type: str
          sample: "Part Component"
        features:
          description: List of baseboard features (cleaned)
          type: list
          elements: str
          sample: ["hosting board", "replaceable"]
        bios:
          description: BIOS information
          type: dict
          contains:
            make:
              description: BIOS vendor
              type: str
              sample: "American Megatrends Inc."
            version:
              description: BIOS version information
              type: dict
              contains:
                id:
                  description: BIOS version
                  type: str
                  sample: "3.4"
            date:
              description: BIOS release date
              type: dict
              contains:
                pretty:
                  description: Human-readable date string
                  type: str
                  sample: "05/21/2021"
                epoch:
                  description: Unix epoch timestamp (if parseable)
                  type: int
                  sample: 1621569600
            features:
              description: List of BIOS features (cleaned)
              type: list
              elements: str
              sample:
                - "PCI"
                - "BIOS is upgradeable"
                - "8042 keyboard (int 9h)"
                - "UEFI"
            languages:
              description: >-
                BIOS languages keyed by language code with enabled status (if
                available)
              type: dict
              sample:
                "en|US|iso8859-1":
                  enabled: true
        interfaces:
          description: Port connector information organized by designator
          type: dict
          sample:
            J1A1:
              PS2Mouse:
                external: "PS/2"
                type: "Mouse Port"
              Keyboard:
                external: "PS/2"
                type: "Keyboard Port"
        ipmi:
          description: IPMI device information
          type: dict
          contains:
            version:
              description: IPMI specification version
              type: dict
              contains:
                id:
                  description: Version identifier
                  type: str
                  sample: "2.0"
        devices:
          description: >-
            Onboard devices keyed by normalized device name (lowercase with
            underscores)
          type: dict
          sample:
            aspeed_video_ast2400:
              type: "video"
              enabled: true
              bus: "0000:08:00.0"
        memory:
          description: Memory information and configuration
          type: dict
          contains:
            type:
              description: Memory type from populated slots
              type: str
              sample: "DDR4"
            synchronous:
              description: Whether memory is synchronous (from type_detail)
              type: bool
              sample: true
            ecc:
              description: Error correction type (simplified)
              type: str
              sample: "multi-bit"
            capacity:
              description: Maximum memory capacity across all arrays
              type: dict
              contains:
                bytes:
                  description: >-
                    Capacity in bytes (requires o0_o.utils collection)
                  type: int
                  sample: 824633720832
                pretty:
                  description: Human-readable capacity with IEC binary units
                  type: str
                  sample: "768 GiB"
        slots:
          description: >-
            All slots (expansion and memory) grouped by normalized type,
            then by index. Type keys are lowercase with underscores,
            numbers removed. Index keys are the slot identifiers.
          type: dict
          sample:
            pci_express:
              "1":
                bus: "0000:81:00.0"
                description: "CPU2 SLOT1 PCI-E 3.0 X8"
                type: "x8 PCI Express 3 x8"
                populated: true
                short: true
                features:
                  - "3.3 V"
                  - "PME signal"
            dimm:
              "P1-DIMMA1":
                description: "P0_Node0_Channel0_Dimm0"
                populated: true
              "P1-DIMMA2":
                description: "P0_Node0_Channel0_Dimm1"
                populated: false
"""


class FilterModule:
    """Filter for parsing dmidecode command output."""

    def filters(self) -> dict[str, Any]:
        """Return the filter functions."""
        return {"dmidecode": self.dmidecode_filter}

    def dmidecode_filter(
        self,
        config: Union[str, list[str], dict[str, Any]],
    ) -> dict[str, Any]:
        """Parse dmidecode output into structured hardware data.

        Parses dmidecode command output into a hierarchical dict
        structure reflecting physical hardware reality.

        :param config: dmidecode command output as string, list, or dict
        :returns: Structured hardware information dict
        :raises AnsibleFilterError: If parsing fails
        """
        try:
            return dmidecode(config)
        except (ValueError, ImportError) as e:
            raise AnsibleFilterError(
                f"dmidecode failed: {type(e).__name__}: {to_native(e)}"
            ) from e
