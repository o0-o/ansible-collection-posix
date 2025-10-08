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
module: read
short_description: Inspect file metadata and optionally content on POSIX hosts
version_added: "1.4.0"
description:
  - Gathers metadata about a file, directory, link, or special device on
    POSIX systems using portable commands and modules.
  - Optionally returns file content when a printable encoding can be
    determined.
  - When the path does not exist the module returns C(null) instead of
    raising an error.
  - Recursive inspection can expand symlink and hard link metadata.
options:
  path:
    description:
      - Absolute path to the file to inspect.
      - Mutually exclusive with I(paths).
    type: str
  content:
    description:
      - Whether to attempt reading the file content when a suitable
        encoding can be established.
    type: bool
    default: false
  metadata:
    description:
      - Whether to include all metadata fields in the result.
      - When C(true) (default), all available metadata fields are included.
      - When C(false), only fields specified by individual field parameters
        are included.
      - This parameter works as a counterpart to I(content), allowing
        selective field inclusion for performance optimization.
    type: bool
    default: true
  type:
    description:
      - Include file type field when I(metadata=false).
      - Ignored when I(metadata=true).
    type: bool
    default: false
  name:
    description:
      - Include file name field when I(metadata=false).
      - Ignored when I(metadata=true).
    type: bool
    default: false
  parent:
    description:
      - Include parent directory field when I(metadata=false).
      - Ignored when I(metadata=true).
    type: bool
    default: false
  mode:
    description:
      - Include file mode/permissions field when I(metadata=false).
      - Ignored when I(metadata=true).
    type: bool
    default: false
  owner:
    description:
      - Include file owner field when I(metadata=false).
      - Ignored when I(metadata=true).
    type: bool
    default: false
  group:
    description:
      - Include file group field when I(metadata=false).
      - Ignored when I(metadata=true).
    type: bool
    default: false
  writable:
    description:
      - Include writable flag when I(metadata=false).
      - Ignored when I(metadata=true).
    type: bool
    default: false
  links:
    description:
      - Include hard link information when I(metadata=false).
      - Ignored when I(metadata=true).
    type: bool
    default: false
  acl:
    description:
      - Include ACL entries when I(metadata=false).
      - Ignored when I(metadata=true).
    type: bool
    default: false
  xattrs:
    description:
      - Include extended attributes when I(metadata=false).
      - Ignored when I(metadata=true).
    type: bool
    default: false
  flags:
    description:
      - Include file flags when I(metadata=false).
      - Ignored when I(metadata=true).
    type: bool
    default: false
  selinux:
    description:
      - Include SELinux context when I(metadata=false).
      - Ignored when I(metadata=true).
    type: bool
    default: false
  encoding:
    description:
      - Override the detected encoding when reading file content.
      - When omitted the action attempts to autodetect a printable
        encoding. If detection fails the content is skipped.
    type: str
  parents:
    description:
      - Control how many parent directories are included for each requested
        path.
      - When C(false) or C(0) (default), parent directories are not added.
      - When C(true), all parents up to the root are included.
      - When a positive integer, that many parents are included, starting at
        the immediate parent.
    type: raw
    default: false
  find_hardlinks:
    description:
      - Enumerate all hard link paths that reference the same inode as
        the requested file.
      - Performs a full scan of the filesystem containing the target
        and can take a very long time on anything larger than small
        mounts such as C(/dev) or other system partitions.
      - Use with extreme caution and only when the additional
        metadata is absolutely required.
    type: bool
    default: false
  find_symlinks:
    description:
      - Enumerate all symbolic links that resolve to the same target as
        the requested path.
      - Performs a full scan of the filesystem containing the target
        and can take a very long time on anything larger than small
        mounts such as C(/dev) or other system partitions.
      - Use with extreme caution and only when the additional
        metadata is absolutely required.
      - When combined with I(find_hardlinks=true) or I(parents=true),
        symbolic links for discovered hard link paths and link targets are
        also reported.
      - When combined with I(find_hardlinks=true) the filesystem is
        traversed only once.
    type: bool
    default: false
  paths:
    description:
      - List of paths to inspect in a single invocation.
      - Mutually exclusive with I(path).
    type: list
    elements: str
author:
  - oØ.o (@o0-o)
notes:
  - This module is implemented as an action plugin and supports raw fallback.
seealso:
  - module: ansible.builtin.stat
    description: Retrieve file or file system status
"""

EXAMPLES = r"""
- name: Gather metadata while leaving binary content untouched
  o0_o.posix.read:
    path: /etc/motd
  register: motd_read

- name: Force UTF-8 decoding and capture file data
  o0_o.posix.read:
    path: /etc/issue
    content: true
    encoding: utf-8
  register: issue_read

- name: Expand metadata for linked targets
  o0_o.posix.read:
    path: /etc/localtime
    parents: true
  register: localtime_read

- name: Discover symlinks pointing at a shared configuration file
  o0_o.posix.read:
    path: /etc/resolv.conf
    find_symlinks: true
  register: resolv_read

- name: Inspect multiple files at once
  o0_o.posix.read:
    paths:
      - /etc/motd
      - /etc/localtime
  register: multi_read

- name: Gather only specific fields for performance
  o0_o.posix.read:
    path: /etc/localtime
    metadata: false
    type: true
    links: true
  register: minimal_read
"""

RETURN = r"""
paths:
  description:
    - Mapping of inspected paths to collected information.
    - When I(find_symlinks=true) additional entries are included for every
      discovered symbolic link that targets a requested path.
  returned: always
  type: dict
  contains:
    /path/to/file:
      description: Metadata for the requested path (C(null) when missing)
      type: dict
      contains:
        type:
          description: File type
          type: str
          sample: regular
        mode:
          description: Octal permission mode
          type: str
          sample: '0644'
        owner:
          description: Owning user name when available
          type: str
          sample: root
        group:
          description: Owning group name when available
          type: str
          sample: wheel
        writable:
          description: Whether the path is writable for the remote user
          type: bool
          sample: true
        name:
          description: Basename of the inspected path
          type: str
          sample: sample
        parent:
          description: Directory containing the inspected path
          type: str
          sample: /etc
        links:
          description:
            - When the path is not a symbolic link and I(find_hardlinks=false),
              this value is an integer representing how many additional hard
              links point to the inode.
            - Otherwise this is a list of related paths such as discovered hard
              links, symlink targets, or symlinks found when
              I(find_symlinks=true).
          type: raw
          sample: ['/path/to/other']
          returned: when link information is available
        acl:
          description:
            - ACL details obtained via getfacl or derived from extended
              attributes when available.
            - Contains keys such as C(text), C(access), and C(default)
              depending on the information collected.
            - A C(type) field indicates the ACL provider (for example
              C(posix), C(macos), C(nfs4)).
          type: dict
          returned: when ACL data is retrievable
          sample: {type: posix, text: '# file: sample'}
        xattrs:
          description: Extended attribute names gathered for the path
          type: list
          elements: str
          returned: when extended attributes are retrievable
          sample: ["user.comment"]
        flags:
          description: Filesystem flags (e.g. immutable) when detectable
          type: list
          elements: str
          returned: when flag information can be gathered
          sample: ['uchg']
        selinux:
          description: SELinux context when provided by the system
          type: str
          returned: on SELinux-enabled systems
          sample: system_u:object_r:etc_t:s0
        encoding:
          description: Encoding used to decode the returned content
          type: str
          returned: when content is included
          sample: utf-8
        content:
          description:
            - For regular files, decoded file content using the reported
              encoding.
            - For directories, a list of direct child paths.
          type: raw
          returned: when readable content is requested and detected, or when
            the path is a directory
"""
from ansible.module_utils.basic import AnsibleModule


def main() -> None:
    """Fail if this module is run directly without the action plugin."""

    argument_spec = {
        "paths": {
            "type": "list",
            "required": True,
            "elements": "str",
            "aliases": ["path"],
        },
        "content": {"type": "bool", "default": False},
        "encoding": {"type": "str"},
        "parents": {"type": "raw", "default": False},
        "find_hardlinks": {"type": "bool", "default": False},
        "find_symlinks": {"type": "bool", "default": False},
    }

    module = AnsibleModule(
        argument_spec=argument_spec, supports_check_mode=True
    )
    module.fail_json(msg="This module must be run via its action plugin.")


if __name__ == "__main__":
    main()
