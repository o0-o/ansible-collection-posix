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
module: stat
short_description: Gather file metadata using stat command
version_added: "1.4.0"
description:
  - Gathers comprehensive metadata about files, directories, links, and
    special devices on POSIX systems.
  - Automatically falls back to parsing stat command output with jc when
    Python is not available on the remote host.
  - Supports checksum calculation, MIME type detection, and file
    attributes.
options:
  path:
    description:
      - The path to the file or directory to stat.
    type: str
    required: true
    aliases: [dest, name]
  follow:
    description:
      - Whether to follow symlinks.
      - When C(true), returns information about the target of the symlink.
      - When C(false), returns information about the symlink itself.
    type: bool
    default: false
  get_checksum:
    description:
      - Whether to calculate and return a checksum for regular files.
      - The checksum algorithm used is controlled by I(checksum_algorithm).
    type: bool
    default: true
  get_mime:
    description:
      - Whether to detect and return the MIME type of the file.
      - Uses the C(file) command to detect MIME types.
    type: bool
    default: true
    aliases: [mime, mime_type]
  get_attributes:
    description:
      - Whether to retrieve file attributes (immutable, append-only, etc).
      - Platform-specific, may not be available on all systems.
    type: bool
    default: true
    aliases: [attr, attributes]
  checksum_algorithm:
    description:
      - The checksum algorithm to use when I(get_checksum=true).
      - Only applies to regular files.
    type: str
    default: sha1
    choices: [md5, sha1, sha224, sha256, sha384, sha512]
    aliases: [checksum, checksum_algo]
author:
  - oØ.o (@o0-o)
notes:
  - This module is implemented as an action plugin and supports raw
    fallback.
  - When running in raw mode (Python unavailable), timestamps have second
    precision only.
  - Some advanced fields like version and generation may not be available
    in raw mode.
seealso:
  - module: ansible.builtin.stat
    description: Retrieve file or file system status
"""

EXAMPLES = r"""
- name: Get file metadata
  o0_o.posix.stat:
    path: /etc/hosts
  register: hosts_stat

- name: Display file size
  ansible.builtin.debug:
    msg: "File size: {{ hosts_stat.stat.size }} bytes"

- name: Get metadata without checksum
  o0_o.posix.stat:
    path: /var/log/messages
    get_checksum: false
  register: log_stat

- name: Follow symlink and get target metadata
  o0_o.posix.stat:
    path: /usr/bin/python
    follow: true
  register: python_stat

- name: Calculate SHA-256 checksum
  o0_o.posix.stat:
    path: /tmp/myfile.txt
    checksum_algorithm: sha256
  register: file_stat
"""

RETURN = r"""
stat:
  description: File metadata dictionary
  returned: always
  type: dict
  contains:
    exists:
      description: Whether the file exists
      type: bool
      returned: always
      sample: true
    path:
      description: Absolute path to the file
      type: str
      returned: always
      sample: /etc/hosts
    size:
      description: Size of the file in bytes
      type: int
      returned: when file exists
      sample: 1234
    mode:
      description: File permissions as octal string
      type: str
      returned: when file exists
      sample: '0644'
    isdir:
      description: Whether the path is a directory
      type: bool
      returned: when file exists
      sample: false
    islnk:
      description: Whether the path is a symbolic link
      type: bool
      returned: when file exists
      sample: false
    isreg:
      description: Whether the path is a regular file
      type: bool
      returned: when file exists
      sample: true
    uid:
      description: User ID of the file owner
      type: int
      returned: when file exists
      sample: 0
    gid:
      description: Group ID of the file owner
      type: int
      returned: when file exists
      sample: 0
    pw_name:
      description: Username of the file owner
      type: str
      returned: when file exists
      sample: root
    gr_name:
      description: Group name of the file owner
      type: str
      returned: when file exists
      sample: wheel
    checksum:
      description: Checksum of the file contents
      type: str
      returned: when file is regular and get_checksum=true
      sample: 1234567890abcdef
    mimetype:
      description: MIME type of the file
      type: str
      returned: when get_mime=true
      sample: text/plain
    atime:
      description: Last access time as Unix timestamp
      type: float
      returned: when file exists
      sample: 1609459200.0
    mtime:
      description: Last modification time as Unix timestamp
      type: float
      returned: when file exists
      sample: 1609459200.0
    ctime:
      description: Last status change time as Unix timestamp
      type: float
      returned: when file exists
      sample: 1609459200.0
"""
from ansible.module_utils.basic import AnsibleModule


def main() -> None:
    """Fail if this module is run directly without the action plugin."""

    argument_spec = {
        "path": {
            "type": "str",
            "required": True,
            "aliases": ["dest", "name"],
        },
        "follow": {"type": "bool", "default": False},
        "get_checksum": {"type": "bool", "default": True},
        "get_mime": {
            "type": "bool",
            "default": True,
            "aliases": ["mime", "mime_type"],
        },
        "get_attributes": {
            "type": "bool",
            "default": True,
            "aliases": ["attr", "attributes"],
        },
        "checksum_algorithm": {
            "type": "str",
            "default": "sha1",
            "choices": [
                "md5",
                "sha1",
                "sha224",
                "sha256",
                "sha384",
                "sha512",
            ],
            "aliases": ["checksum", "checksum_algo"],
        },
    }

    module = AnsibleModule(
        argument_spec=argument_spec, supports_check_mode=True
    )
    module.fail_json(msg="This module must be run via its action plugin.")


if __name__ == "__main__":
    main()
