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

from __future__ import absolute_import, division, print_function
from __future__ import annotations

DOCUMENTATION = r"""
---
module: mounts
short_description: Gather filesystem mount information
version_added: "1.4.0"
description:
  - Gathers information about mounted filesystems on the target system.
  - Combines data from the C(mount) and C(df -P) commands to provide
    comprehensive mount point information.
  - Also parses C(/etc/fstab) to provide configured mount points.
  - Returns device names, filesystem types, and capacity information
    where available.
  - By default, excludes virtual and pseudo filesystems, but includes
    network filesystems.
  - Does not require Python on the target host.
options:
  device:
    description:
      - Include device-backed filesystems in the output.
      - Device filesystems are those backed by block devices.
    type: bool
    default: true
    version_added: "2.0.0"
  virtual:
    description:
      - Include virtual filesystems in the output.
      - Virtual filesystems include memory-based and special purpose
        filesystems like tmpfs, autofs, etc.
    type: bool
    default: false
    version_added: "2.0.0"
  network:
    description:
      - Include network filesystems in the output.
      - Network filesystems include nfs, nfs4, cifs, smbfs, sshfs, etc.
    type: bool
    default: true
    version_added: "2.0.0"
  pseudo:
    description:
      - Include pseudo filesystems in the output.
      - Pseudo filesystems are kernel interfaces like proc, sysfs,
        debugfs, etc.
      - If not specified, defaults to the value of I(virtual).
    type: bool
    version_added: "2.0.0"
  overlay:
    description:
      - Include overlay filesystems in the output.
    type: bool
    default: true
    version_added: "2.0.0"
  fuse:
    description:
      - Include FUSE (Filesystem in Userspace) filesystems in the output.
    type: bool
    default: true
    version_added: "2.0.0"
author:
  - oØ.o (@o0-o)
notes:
  - The module runs the C(mount) command to get mount information.
  - It also runs C(df -P) to get capacity information when available.
  - It reads and parses C(/etc/fstab) to provide configured mount points.
  - If C(df) is not available, mount information is still returned
    without capacity data.
  - If C(/etc/fstab) cannot be read, an empty list is returned for fstab.
  - Virtual filesystems (excluded by default) include memory-based and
    special purpose filesystems.
  - Pseudo filesystems (excluded by default) are a subset of virtual
    filesystems specifically for kernel interfaces.
  - Network filesystems (included by default) are remote/network-mounted
    filesystems.
attributes:
  check_mode:
    description: This module supports check mode.
    support: full
  async:
    description: This module does not support async operation.
    support: none
  platform:
    description: Only POSIX platforms are supported.
    support: full
    platforms: posix
"""

EXAMPLES = r"""
- name: Gather filesystem information
  o0_o.posix.filesystems:
  register: mount_info

- name: Display all mount points
  ansible.builtin.debug:
    msg: "Mount points: {{ mount_info.mounts.keys() | list }}"

- name: Show root filesystem information
  ansible.builtin.debug:
    var: mount_info.mounts['/']
  when: "'/' in mount_info.mounts"

- name: Get filesystems including virtual filesystems
  o0_o.posix.filesystems:
    include_virtual: true
  register: all_mounts

- name: Get only physical and network filesystems
  o0_o.posix.filesystems:
    include_virtual: false
    include_network: true
    include_pseudo: false
  register: physical_mounts

- name: Get only local physical filesystems (no network)
  o0_o.posix.filesystems:
    include_virtual: false
    include_network: false
    include_pseudo: false
  register: local_mounts

- name: Find mounts with low space (< 10% free)
  ansible.builtin.set_fact:
    low_space_mounts: |
      {%- set result = [] -%}
      {%- for mount, info in mount_info.mounts.items() -%}
        {%- if info.capacity is defined -%}
          {%- set used = info.capacity.used.value -%}
          {%- set total = info.capacity.total.value -%}
          {%- set percent_used = (used / total * 100) | round -%}
          {%- if percent_used > 90 -%}
            {%- set _ = result.append({
              'mount': mount,
              'device': info.device,
              'percent_used': percent_used
            }) -%}
          {%- endif -%}
        {%- endif -%}
      {%- endfor -%}
      {{ result }}
  when: mount_info.mounts

- name: Display fstab entries
  ansible.builtin.debug:
    msg: "Configured: {{ item.source }} on {{ item.mount }} ({{ item.type }})"
  loop: "{{ mount_info.fstab }}"
  when: mount_info.fstab

- name: Find fstab entries not currently mounted
  ansible.builtin.set_fact:
    unmounted_fstab: >-
      {{ mount_info.fstab
         | selectattr('mount', 'ne', None)
         | rejectattr('mount', 'in', mount_info.mounts.keys())
         | list }}
"""

RETURN = r"""
mounts:
  description: Dictionary of mounted filesystems
  returned: always
  type: dict
  contains:
    <mount_point>:
      description: Information about a specific mount point
      type: dict
      contains:
        device:
          description: Device or source of the mount
          type: str
          sample: "/dev/sda1"
        filesystem:
          description: Filesystem type
          type: str
          sample: "ext4"
        capacity:
          description: Capacity information from df command
          returned: when df command is available
          type: dict
          contains:
            total:
              description: Total capacity
              type: dict
              contains:
                value:
                  description: Total capacity in bytes
                  type: int
                  sample: 10737418240
                unit:
                  description: Unit of measurement
                  type: str
                  sample: "B"
            used:
              description: Used capacity
              type: dict
              contains:
                value:
                  description: Used capacity in bytes
                  type: int
                  sample: 5368709120
                unit:
                  description: Unit of measurement
                  type: str
                  sample: "B"
  sample:
    "/":
      device: "/dev/sda1"
      filesystem: "ext4"
      capacity:
        total:
          value: 10737418240
          unit: "B"
        used:
          value: 5368709120
          unit: "B"
    "/boot":
      device: "/dev/sda2"
      filesystem: "ext4"
      capacity:
        total:
          value: 524288000
          unit: "B"
        used:
          value: 104857600
          unit: "B"
    "/home":
      device: "/dev/sdb1"
      filesystem: "xfs"
      capacity:
        total:
          value: 107374182400
          unit: "B"
        used:
          value: 21474836480
          unit: "B"
fstab:
  description: List of parsed /etc/fstab entries
  returned: always
  type: list
  elements: dict
  contains:
    source:
      description: Device or filesystem source
      type: str
      sample: "/dev/sda1"
    mount:
      description: Mount point (null for swap)
      type: str
      sample: "/"
    type:
      description: Filesystem type
      type: str
      sample: "ext4"
    options:
      description: Mount options as list of dicts
      type: list
      elements: dict
      sample:
        - defaults: true
        - noatime: true
    dump:
      description: Dump frequency (null if omitted in fstab)
      type: int
      sample: 0
    pass:
      description: Fsck pass number (null if omitted in fstab)
      type: int
      sample: 1
  sample:
    - source: "/dev/sda1"
      mount: "/"
      type: "ext4"
      options:
        - defaults: true
        - noatime: true
      dump: 0
      pass: 1
    - source: "/dev/sda2"
      mount: "/home"
      type: "ext4"
      options:
        - defaults: true
      dump: 0
      pass: 2
mount_count:
  description: Number of mounted filesystems found
  returned: always
  type: int
  sample: 3
msg:
  description: Summary message
  returned: always
  type: str
  sample: "Found 3 mounted filesystem(s)"
changed:
  description: Always false as this is an information gathering module
  returned: always
  type: bool
  sample: false
"""

from ansible.module_utils.basic import AnsibleModule


def main() -> None:
    """Fail if this module is run directly without the action plugin."""

    argument_spec = {
        "device": {"type": "bool", "default": True},
        "virtual": {"type": "bool", "default": False},
        "network": {"type": "bool", "default": True},
        "pseudo": {"type": "bool", "default": None},
        "overlay": {"type": "bool", "default": True},
        "fuse": {"type": "bool", "default": True},
    }

    module = AnsibleModule(
        argument_spec=argument_spec, supports_check_mode=True
    )
    module.fail_json(msg="This module must be run via its action plugin.")


if __name__ == "__main__":
    main()
