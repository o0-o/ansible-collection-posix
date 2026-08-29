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
  - Returns what is mounted where, the filesystem type and options
    C(mount) reports, and the capacity C(df) reports.
  - Returns the same C(mounts) shape M(o0_o.posix.facts) publishes
    under C(o0_storage.mounts), built by the same composition.
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
  - It also runs C(df -P) to get capacity information.
  - It reads and parses C(/etc/fstab) to provide configured mount points.
  - Capacity is what C(df) alone knows, so C(df) names what gets
    reported - a mount point only C(mount) named is left out rather
    than reported without its capacity, and a host where C(df) cannot
    run fails the task rather than answering with half the fact.
  - Where C(df) and C(mount) disagree about a mount point's source,
    C(df) is taken and the disagreement is logged at C(-vvv).
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
- name: Gather mounted filesystems
  o0_o.posix.mounts:
  register: mount_info

- name: Display all mount points
  ansible.builtin.debug:
    msg: "Mount points: {{ mount_info.mounts.keys() | list }}"

- name: Show root filesystem information
  ansible.builtin.debug:
    var: mount_info.mounts['/']
  when: "'/' in mount_info.mounts"

- name: Include virtual and pseudo filesystems
  o0_o.posix.mounts:
    virtual: true
  register: all_mounts

- name: Report only local filesystems on block devices
  o0_o.posix.mounts:
    network: false
    overlay: false
    fuse: false
  register: local_mounts

- name: Find mounts with less than ten percent free
  ansible.builtin.set_fact:
    low_space_mounts: >-
      {{ mount_info.mounts
         | dict2items(key_name='mount', value_name='info')
         | selectattr('info.capacity.used.percent', 'gt', 90)
         | list }}

- name: Name a mount's source, whatever kind of source it is
  ansible.builtin.debug:
    msg: >-
      {{ item.key }} is
      {{ item.value.source.path
         | default(item.value.source.address)
         | default(item.value.source.name)
         | default('unnamed') }}
  loop: "{{ mount_info.mounts | dict2items }}"

- name: Read a mount option by its normalized name
  ansible.builtin.debug:
    msg: "/ is writable: {{ mount_info.mounts['/'].options.writable }}"
  when: mount_info.mounts['/'].options.writable is defined

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
  description: >-
    What is mounted, keyed by mount point. Composed from C(df) and
    C(mount) together, so a mount point C(df) did not report is not
    reported here either. M(o0_o.posix.facts) publishes the same
    composition under C(o0_storage.mounts).
  returned: always
  type: dict
  contains:
    source:
      description: >-
        What is mounted there, as C(df) named it - a C(path) for a
        device, an C(address) for a network export, a C(uuid) or
        C(label) for a named volume, a C(map) for an automounter, or a
        C(name) for a special filesystem. Null where the source is
        C(none) or C(-).
      type: dict
      sample:
        path: /dev/sda1
    type:
      description: Filesystem type, as C(mount) named it
      returned: when mount reported the mount point too
      type: str
      sample: ext4
    options:
      description: >-
        The options it was mounted with, merged into one dict with
        normalized names - C(ro) reads as C(writable: false), C(nosuid)
        as C(suid: false), the C(atime) family collapses into a single
        C(atime) enum of C(true), C(false), C(relative) or C(strict),
        and an option carrying a value keeps it. This is a dict where
        the C(fstab) return's C(options) is a list of dicts, because
        C(mount) reports the options in effect while C(fstab) records
        the order they were written in.
      returned: when mount reported the mount point too
      type: dict
      sample:
        writable: true
        suid: false
        atime: relative
    capacity:
      description: How much of the filesystem C(df) reported in use.
      type: dict
      contains:
        total:
          description: Size of the filesystem
          type: dict
          contains:
            bytes:
              description: Size in bytes
              type: int
              sample: 10737418240
            pretty:
              description: Size in binary units
              type: str
              sample: 10.00 GiB
        used:
          description: Space in use
          type: dict
          contains:
            bytes:
              description: Bytes in use
              type: int
              sample: 5368709120
            pretty:
              description: Space in use, in binary units
              type: str
              sample: 5.00 GiB
            percent:
              description: >-
                Share of the filesystem in use, computed from the byte
                counts rather than taken from C(df)
              type: float
              sample: 50.0
  sample:
    "/":
      source:
        path: /dev/sda1
      type: ext4
      options:
        writable: true
        atime: relative
      capacity:
        total:
          bytes: 10737418240
          pretty: 10.00 GiB
        used:
          bytes: 5368709120
          pretty: 5.00 GiB
          percent: 50.0
    /home:
      source:
        uuid: 1b0f9a2c-6d31-4e5a-9c77-2f4d8e6a1b03
        partition: false
      type: xfs
      options:
        writable: true
      capacity:
        total:
          bytes: 107374182400
          pretty: 100.00 GiB
        used:
          bytes: 21474836480
          pretty: 20.00 GiB
          percent: 20.0
fstab:
  description: >-
    The entries C(/etc/fstab) names, in file order, or an empty list
    where the file could not be read. Every key is present on every
    entry, null where the file omitted the field.
    M(o0_o.posix.facts) publishes the same list under
    C(o0_paths['/etc/fstab']['config']), where what a file configures
    is a fact about that file.
  returned: always
  type: list
  elements: dict
  contains:
    source:
      description: >-
        What to mount, as the file spells it - a device path, or a
        C(UUID=) or C(LABEL=) form, left unparsed
      type: str
      sample: UUID=abc-123
    mount:
      description: Where to mount it, null for swap
      type: str
      sample: /
    type:
      description: >-
        Filesystem type, or the list of them where the field named
        more than one
      type: raw
      sample: ext4
    options:
      description: >-
        Mount options in file order, one single-key dict each, the
        value C(true) for a flag and the string for an option carrying
        one. A list of dicts where the C(mounts) return's C(options) is
        a merged dict.
      type: list
      elements: dict
      sample:
        - defaults: true
        - noatime: true
    dump:
      description: Dump frequency, null if the file omitted it
      type: int
      sample: 0
    pass:
      description: Fsck pass number, null if the file omitted it
      type: int
      sample: 1
  sample:
    - source: UUID=abc-123
      mount: /
      type: ext4
      options:
        - defaults: true
        - noatime: true
      dump: 0
      pass: 1
    - source: /dev/sda2
      mount: null
      type: swap
      options:
        - sw: true
      dump: 0
      pass: 0
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
