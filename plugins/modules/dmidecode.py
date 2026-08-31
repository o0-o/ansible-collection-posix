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
module: dmidecode
short_description: Gather hardware information using dmidecode
version_added: "2.0.0"
description:
  - Executes the C(dmidecode) command and parses the output into
    structured hardware information.
  - Returns hierarchical dict structure reflecting physical hardware
    reality.
  - Requires root/sudo privileges on the target system.
options: {}
requirements:
  - dmidecode command on target system
  - Root/sudo privileges
  - jc library on controller
author:
  - oØ.o (@o0-o)
notes:
  - This module is implemented as an action plugin.
  - The dmidecode command typically requires root privileges.
  - "Use C(become: true) when calling this module."
"""

EXAMPLES = r"""
- name: Gather hardware information
  o0_o.posix.dmidecode:
  become: true
  register: hardware_info

- name: Display system manufacturer and model
  ansible.builtin.debug:
    msg: "{{ hardware_info.hardware.make }} {{ hardware_info.hardware.model }}"

- name: Show BIOS version
  ansible.builtin.debug:
    msg: "BIOS {{ hardware_info.hardware.baseboard.bios.version.id }}"

- name: List processors
  ansible.builtin.debug:
    msg: "{{ item.key }}: {{ item.value.make }} {{ item.value.model.pretty }}"
  loop: "{{ hardware_info.hardware.processors | dict2items }}"

- name: Show memory configuration
  ansible.builtin.debug:
    msg: >-
      Total capacity: {{
        hardware_info.hardware.baseboard.memory.capacity.pretty
      }}
"""

RETURN = r"""
hardware:
  description: Structured hardware information from dmidecode
  returned: success
  type: dict
  contains:
    make:
      description: System manufacturer
      type: str
      sample: "Supermicro"
    model:
      description: System product name/model
      type: str
      sample: "SSG-6028R-E1CR24L"
    baseboard:
      description: Baseboard/motherboard information
      type: dict
      contains:
        make:
          description: Baseboard manufacturer
          type: str
          sample: "Supermicro"
        model:
          description: Baseboard model
          type: str
          sample: "X10DSC+"
        bios:
          description: BIOS information
          type: dict
          contains:
            make:
              description: BIOS vendor
              type: str
              sample: "American Megatrends Inc."
            version:
              description: BIOS version
              type: dict
              contains:
                id:
                  description: Version string
                  type: str
                  sample: "3.4"
    processors:
      description: >-
        Processor models grouped the way memory groups part numbers -
        the model states its spec once and each socket that holds one
        files what it alone knows under C(locations), keyed by socket
        designation
      type: dict
      sample:
        intel_xeon_cpu_e5_2690_v3:
          make: "Intel"
          model:
            name: "intel_xeon_cpu_e5_2690_v3"
            pretty: "Intel(R) Xeon(R) CPU E5-2690 v3 @ 2.60GHz"
          cores:
            total: 12
          speed:
            max:
              hertz: 3500000000
              pretty: "3.5 GHz"
          locations:
            cpu1:
              cores:
                enabled: 12
              speed:
                current:
                  hertz: 2600000000
                  pretty: "2.6 GHz"
            cpu2:
              cores:
                enabled: 12
              speed:
                current:
                  hertz: 2600000000
                  pretty: "2.6 GHz"
    memory:
      description: >-
        Memory modules grouped by part number, each carrying the
        locations it occupies keyed by bank locator and locator
      type: dict
    power:
      description: Power supplies grouped by model
      type: dict
    chassis:
      description: Chassis information
      type: dict
"""

from ansible.module_utils.basic import AnsibleModule


def main() -> None:
    """Fail if this module is run directly without the action plugin."""

    module = AnsibleModule(argument_spec={}, supports_check_mode=True)
    module.fail_json(msg="This module must be run via its action plugin.")


if __name__ == "__main__":
    main()
