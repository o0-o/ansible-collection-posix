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
from ansible_collections.o0_o.posix.plugins.module_utils import (
    mount,
)

DOCUMENTATION = r"""
---
name: mount
short_description: Parse mount command output
version_added: "1.4.0"
description:
  - Parse output from the mount command into structured data using jc
  - Returns a list of mount entries, one per mounted filesystem
  - Unidirectional filter (parse only, no generation)
options:
  _input:
    description:
      - Command output from 'mount' as string, list of lines, or
        command result dict
    type: raw
    required: true
requirements:
  - jc (Python library)
notes:
  - The jc library parses mount output into structured data
  - Entries name the same four things an fstab entry does, minus
    C(dump) and C(pass), but two of them carry a different shape than
    the fstab filter gives them
  - C(source) is a structured dict, not the raw string the fstab filter
    returns
  - Options are merged into a single dict, not the list of dicts the
    fstab filter returns, and their names are normalized rather than
    kept as mount printed them
  - Type is always a string (never a list)
author:
  - oØ.o (@o0-o)
"""

EXAMPLES = r"""
# Parse mount output
- name: Get mount information
  ansible.builtin.command:
    cmd: mount
  register: mount_result

- name: Parse mount output and store
  ansible.builtin.set_fact:
    mount_info: "{{ mount_result.stdout | o0_o.posix.mount }}"

- name: Display root filesystem info
  vars:
    root_fs: >-
      {{ mount_info | selectattr('mount', 'equalto', '/') | first }}
  ansible.builtin.debug:
    msg: >-
      Root mounted from {{ root_fs.source.path }} as {{ root_fs.type }}

- name: Fail when the root filesystem is mounted read-only
  ansible.builtin.assert:
    that:
      - root_fs.options.writable | default(false)
  vars:
    root_fs: >-
      {{ mount_info | selectattr('mount', 'equalto', '/') | first }}
"""

RETURN = r"""
_value:
  description: List of mount entries with standardized structure
  type: list
  elements: dict
  returned: always
  contains:
    source:
      description:
        - What is mounted, parsed into whichever fields the source
          names, C(null) for the sources C(none) and C(-).
        - One of C(path) for a device or bind path, C(address) for an
          NFS or SMB target, C(name) for a special filesystem such as
          C(proc), C(map) for an automounter map, or C(uuid) or
          C(label) with a C(partition) boolean saying whether the
          C(PART) form was used.
      type: dict
      sample:
        path: /dev/sda1
    mount:
      description: Mount point
      type: str
      sample: /
    type:
      description: >-
        Filesystem type, taken from the type field where mount prints
        one and from the first option where it does not (macOS,
        FreeBSD); C(null) when neither is available
      type: str
      sample: ext4
    options:
      description:
        - Mount options merged into one dict, with normalized names
          rather than the names mount printed.
        - C(rw) and C(ro) become C(writable), C(sync) and C(async)
          become C(sync), C(hard) and C(soft) become C(hard).
        - The atime family collapses into a single C(atime) whose value
          is C(true) for C(atime), C(false) for C(noatime),
          C(relative) for C(relatime), or C(strict) for
          C(strictatime).
        - A C(no)-prefixed option becomes its positive name set to
          C(false), so C(nosuid) becomes C(suid=false).
        - An option carrying a value keeps its own name, with the value
          as a string.
        - Any other flag becomes its own name set to C(true).
      type: dict
      sample:
        writable: true
        atime: relative
        errors: remount-ro
  sample:
    - source:
        path: /dev/sda1
      mount: /
      type: ext4
      options:
        writable: true
        atime: relative
        errors: remount-ro
    - source:
        name: proc
      mount: /proc
      type: proc
      options:
        writable: true
        suid: false
        dev: false
        exec: false
        atime: relative
    - source:
        address: server:/export
      mount: /mnt/nfs
      type: nfs
      options:
        writable: true
        vers: '4.2'
        rsize: '1048576'
        wsize: '1048576'
"""


class FilterModule:
    """Filter for parsing mount command output."""

    def filters(self) -> dict[str, Any]:
        """Return the filter functions."""
        return {"mount": self.mount_filter}

    def mount_filter(
        self,
        config: Union[str, dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Parse mount output into structured data.

        Parses mount command output into normalized list of entries
        naming the same things an fstab entry does, minus dump and
        pass:
        - filesystem → source (structured, not the raw string)
        - mount_point → mount
        - type field or first option → type
        - remaining options → options (as one merged dict with
          normalized names, not fstab's list of dicts)

        :param config: Mount command output as string, list, or dict
        :returns: List of mount entries with standardized structure
        :raises AnsibleFilterError: If parsing fails
        """
        try:
            return mount(config)
        except (ValueError, ImportError) as e:
            raise AnsibleFilterError(f"mount failed: {to_native(e)}") from e
