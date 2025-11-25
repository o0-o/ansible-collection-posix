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
  paths:
    description:
      - List of paths to inspect in a single invocation.
      - Can also be specified as a single path string using the I(path)
        alias.
    type: list
    elements: str
    required: true
    aliases: [path]
  include:
    description:
      - List of fields to include in the result.
      - C(all) includes everything (metadata + extended + content + children).
      - C(metadata) includes basic metadata and extended filesystem
        attributes such as type, mode, owner, group, size, writable,
        hardlinks, inode, timestamps (modified, created, changed), ACL,
        filesystem flags, and SELinux context (but NOT xattrs).
      - C(extended) includes all metadata plus extended attributes (xattrs).
      - C(content) includes file content with encoding detection.
      - C(children) includes directory child paths.
    type: list
    elements: str
    default: ['metadata']
    choices:
      - all
      - metadata
      - extended
      - content
      - children
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
  follow:
    description:
      - How to handle symbolic links.
      - Can be a boolean or the string C(recurse).
      - When C(true) (default), resolves to the ultimate target (like
        C(readlink -f)).
      - When C(recurse), adds link targets to the paths list recursively
        until a non-symlink is found.
      - When C(false), lists the link without following or recursing.
    type: raw
    default: true
  children:
    description:
      - Recursively read child entries within directories.
      - Can be a boolean or a positive integer.
      - When C(true), enables unlimited recursion into all subdirectories.
      - When a positive integer, sets maximum directory depth to descend.
      - When C(false) or C(0) (default), child recursion is disabled.
      - Has no effect on non-directory entries.
    type: raw
    default: false
author:
  - oØ.o (@o0-o)
notes:
  - This module is implemented as an action plugin and supports raw fallback.
seealso:
  - module: ansible.builtin.stat
    description: Retrieve file or file system status
"""

EXAMPLES = r"""
- name: Gather basic metadata (default)
  o0_o.posix.read:
    path: /etc/motd
  register: motd_read

- name: Include file content with metadata
  o0_o.posix.read:
    path: /etc/issue
    include: ['content', 'metadata']
  register: issue_read

- name: Include extended attributes (xattrs)
  o0_o.posix.read:
    path: /etc/ssh/sshd_config
    include: ['extended']
  register: sshd_config_read

- name: Expand metadata for parent directories
  o0_o.posix.read:
    path: /etc/localtime
    parents: true
  register: localtime_read

- name: Recursively read directory contents
  o0_o.posix.read:
    path: /etc/ssh
    children: true
  register: ssh_dir_read

- name: Follow symlinks to ultimate target
  o0_o.posix.read:
    path: /etc/resolv.conf
    follow: true
  register: resolv_read

- name: Read symlink without following
  o0_o.posix.read:
    path: /etc/localtime
    follow: false
  register: localtime_link_read

- name: Inspect multiple files at once
  o0_o.posix.read:
    paths:
      - /etc/motd
      - /etc/issue
      - /etc/hostname
  register: multi_read

- name: Include everything (all metadata, content, children)
  o0_o.posix.read:
    path: /var/log
    include: ['all']
    children: 2
  register: full_read
"""

RETURN = r"""
paths:
  description:
    - Mapping of inspected paths to collected information.
    - When I(follow=recurse), additional entries are included for all symlink
      targets in the resolution chain.
    - When I(children) is enabled, additional entries are included for all
      discovered child paths.
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
        hardlinks:
          description:
            - For regular files, the count of OTHER hard links pointing to
              the same inode (total link count minus 1).
            - Only present when the count is greater than 0.
          type: int
          sample: 1
          returned: when hardlinks > 0
        inode:
          description:
            - The inode number of the file.
            - Only present when hardlinks > 0 to help identify related files.
          type: int
          sample: 12345678
          returned: when hardlinks > 0
        target:
          description:
            - For symbolic links, the path that the link points to.
            - Can be a relative or absolute path.
          type: str
          sample: /path/to/target
          returned: when type is link
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
            - Decoded file content using the reported encoding.
            - Only present when I(include) contains C(content) or C(all).
          type: str
          returned: when content is requested and readable
        children:
          description:
            - List of child paths for directories.
            - Only present when I(include) contains C(children) or C(all),
              or when I(children) parameter is enabled.
          type: list
          elements: str
          returned: when path is a directory and children are requested
          sample: ['/etc/ssh/ssh_config', '/etc/ssh/sshd_config']
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
        "include": {
            "type": "list",
            "elements": "str",
            "default": ["metadata"],
            "choices": [
                "all",
                "metadata",
                "extended",
                "content",
                "children",
            ],
        },
        "parents": {"type": "raw", "default": False},
        "follow": {"type": "raw", "default": True},
        "children": {"type": "raw", "default": False},
    }

    module = AnsibleModule(
        argument_spec=argument_spec, supports_check_mode=True
    )
    module.fail_json(msg="This module must be run via its action plugin.")


if __name__ == "__main__":
    main()
