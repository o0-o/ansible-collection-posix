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

__metaclass__ = type


DOCUMENTATION = r"""
---
module: mounts
short_description: Gather filesystem mount information
version_added: "1.4.0"
description:
  - Gathers information about mounted filesystems on the target system.
  - Combines data from the C(mount) and C(df -P) commands to provide
    comprehensive mount point information.
  - Returns device names, filesystem types, and capacity information
    where available.
  - By default, excludes virtual and pseudo filesystems, but includes
    network filesystems.
  - Does not require Python on the target host.
options:
  include_virtual:
    description:
      - Include virtual filesystems in the output.
      - Virtual filesystems include memory-based and special purpose
        filesystems like tmpfs, overlay, autofs, etc.
    type: bool
    default: false
  include_network:
    description:
      - Include network filesystems in the output.
      - Network filesystems include nfs, nfs4, cifs, smbfs, sshfs, etc.
    type: bool
    default: true
  include_pseudo:
    description:
      - Include pseudo filesystems in the output.
      - Pseudo filesystems are kernel interfaces like proc, sysfs,
        debugfs, etc.
      - If not specified, defaults to the value of include_virtual.
    type: bool
    default: null
author:
  - oØ.o (@o0-o)
notes:
  - The module runs the C(mount) command to get mount information.
  - It also runs C(df -P) to get capacity information when available.
  - If C(df) is not available, mount information is still returned
    without capacity data.
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
