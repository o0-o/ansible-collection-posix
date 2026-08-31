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
module: read
short_description: Inspect file metadata and optionally content on POSIX hosts
version_added: "2.0.0"
description:
  - Gathers metadata about a file, directory, link, or special device on
    POSIX systems using portable commands and modules.
  - Optionally returns file content when a printable encoding can be
    determined.
  - When the path does not exist the module returns C(null) instead of
    raising an error.
  - Each class of information is requested with its own option, so a task
    reads as the set of facts it needs.
  - Recursive inspection can expand parent directories, directory
    children, and symlink targets.
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
  attributes:
    description:
      - Include basic metadata and extended filesystem attributes such as
        type, mode, uid, gid, size, readable, writable, executable,
        hardlinks, inode, timestamps (modified, created, changed), ACL,
        filesystem flags, and SELinux context.
      - Does not include extended attributes (xattrs); use I(extended)
        for those.
      - Defaults to C(false) when I(content) or I(lines) is requested and
        this option is not set explicitly.
    type: bool
    default: true
  extended:
    description:
      - Include extended attributes (xattrs).
      - Implies I(attributes=true).
    type: bool
    default: false
  content:
    description:
      - Include file content with encoding detection.
      - The content is the file's bytes, trailing newline included.
      - Text content is POSIX text, which the standard defines as lines
        terminated by newline alone. Carriage returns are normalized
        away, C(\r\n) and lone C(\r) alike, on every transport. A file
        whose exact bytes matter is read with C(encoding) set to
        C(base64), which answers byte for byte.
      - Binary content is returned base64 encoded. A file the C(file)
        command calls binary for want of magic to match, which is any
        file of a few bytes and the empty file, is still read as text
        when its bytes decode as UTF-8 and hold nothing but printable
        characters and ordinary whitespace.
      - An encoding the C(file) command names from a single-byte family
        is settled the same way, because a C(file) with no magic for
        UTF-8 answers C(ISO-8859) for it and Latin-1 decodes any byte
        at all. Content holding non-ASCII bytes that decode strictly as
        UTF-8 is read as UTF-8; content that is genuinely single-byte
        fails that decode and keeps the detected encoding. This applies
        to auto-detection only; an encoding set with I(encoding) is
        used exactly as given.
      - Only regular files are read. A directory, symlink, FIFO, socket
        or device is reported with no C(content) key and no error; its
        C(type) says why.
    type: bool
    default: false
  lines:
    description:
      - Include file content split into a list of lines.
      - Only returned for content that decodes to text; binary content
        is returned as C(content) with a C(base64) or C(hex) encoding
        instead.
      - Reads only regular files, exactly as I(content) does.
    type: bool
    default: false
  encoding:
    description:
      - Force a specific encoding instead of auto-detection.
      - Supports standard encodings (C(utf-8), C(iso-8859-1),
        C(shift-jis), and so on), C(base64) for binary data, and C(hex)
        for a hexadecimal representation.
      - Fails when the content cannot be decoded with the given encoding.
      - Implies I(content=true).
    type: str
  mime:
    description:
      - Detect the MIME type using the C(file) command.
      - Fails when the C(file) command is unavailable.
    type: bool
    default: false
  md5:
    description:
      - Calculate the MD5 checksum of the file content.
    type: bool
    default: false
  sha1:
    description:
      - Calculate the SHA-1 checksum of the file content.
    type: bool
    default: false
  sha256:
    description:
      - Calculate the SHA-256 checksum of the file content.
    type: bool
    default: false
  sha512:
    description:
      - Calculate the SHA-512 checksum of the file content.
    type: bool
    default: false
  parents:
    description:
      - Control how many parent directories are included for each
        requested path.
      - When C(false) or C(0) (default), parent directories are not
        added.
      - When C(true), all parents up to the root are included.
      - When a positive integer, that many parents are included, starting
        at the immediate parent.
    type: raw
    default: false
  follow:
    description:
      - How to handle symbolic links.
      - Can be a boolean or the string C(recursive).
      - When C(true) (default), resolves to the ultimate target (like
        C(readlink -f)) and reports the target's metadata under the
        requested path, adding a C(realpath) key.
      - When C(recursive), adds link targets to the paths list
        recursively until a non-symlink is found.
      - When C(false), lists the link without following or recursing.
    type: raw
    default: true
  resolve:
    description:
      - Walk each path through every symbolic link it passes through and
        report the walk under C(resolution), an ordered list of the
        absolute paths visited, ending at the canonical path.
      - A directory component is a hop like any other. Where C(/bin) is
        itself a link to C(usr/bin) and C(/bin/sh) is a link to C(bash),
        resolving C(/bin/sh) reports
        C([/bin/sh, /usr/bin/sh, /usr/bin/bash]).
      - A path that is nothing but itself resolves to a chain of one.
      - A link whose target is not there is walked to that target all
        the same, and the chain's last step is the path that is
        missing.
      - A chain that returns to a path it has already visited never
        ends, so the module fails and names the cycle rather than
        publishing a prefix of an infinite list.
      - Independent of I(follow), which decides whose metadata the
        entry carries. A resolved link still reports the chain it
        walked, whatever entry it ends up holding.
    type: bool
    default: false
  list:
    description:
      - Add a C(children) field to directory entries containing the list
        of child paths.
      - Independent of I(children), which controls recursive reading.
    type: bool
    default: false
  children:
    description:
      - Recursively read child entries within directories.
      - Can be a boolean or a positive integer.
      - When C(true), enables unlimited recursion into all
        subdirectories.
      - When a positive integer, sets maximum directory depth to descend.
      - When C(false) or C(0) (default), child recursion is disabled.
      - Implies I(list=true). Has no effect on non-directory entries.
    type: raw
    default: false
  raw:
    description:
      - Control raw execution mode behavior.
      - 'C(true): Force raw fallback mode, bypassing native Python.'
      - 'C(false): Force native Python execution (fail if unavailable).'
      - 'C("auto"): Automatically detect and use the best method.'
      - Useful for debugging, testing, or bootstrap scenarios.
    type: raw
    default: "auto"
author:
  - oØ.o (@o0-o)
notes:
  - This module is implemented as an action plugin and supports raw fallback.
  - Requesting I(content) or I(lines) turns I(attributes) off unless it is
    set explicitly, so content reads stay cheap.
  - The type of every path and the target of every link are always
    determined, the C(ls) that reports them running in every batch, and
    I(attributes) governs only whether they are published. I(children)
    recursion and I(follow) therefore behave the same whether or not a
    C(type) or C(target) key appears in the result.
  - Content is read in a second command batch, once the first has typed
    every path, because reading a FIFO with no writer would otherwise
    block until the connection timed out. A read that asks for no
    content, or whose paths are all directories or special files, costs
    no extra round trip.
  - Child entries are only expanded for the paths named in I(paths), not
    for directories added by I(parents).
seealso:
  - module: ansible.builtin.stat
    description: Retrieve file or file system status
  - module: o0_o.posix.write
    description: Write files on POSIX hosts
"""

EXAMPLES = r"""
- name: Gather basic metadata (default)
  o0_o.posix.read:
    path: /etc/motd
  register: motd_read

- name: Read file content
  o0_o.posix.read:
    path: /etc/issue
    content: true
  register: issue_read

- name: Read file content as lines, with metadata
  o0_o.posix.read:
    path: /etc/hosts
    lines: true
    attributes: true
  register: hosts_read

- name: Read a binary file as base64
  o0_o.posix.read:
    path: /bin/sh
    content: true
    encoding: base64
  register: sh_read

- name: Include extended attributes (xattrs)
  o0_o.posix.read:
    path: /etc/ssh/sshd_config
    extended: true
  register: sshd_config_read

- name: Checksum and identify a file
  o0_o.posix.read:
    path: /etc/localtime
    mime: true
    sha256: true
  register: localtime_read

- name: Expand metadata for parent directories
  o0_o.posix.read:
    path: /etc/ssh/sshd_config
    parents: true
  register: sshd_parents_read

- name: List the entries of a directory
  o0_o.posix.read:
    path: /etc/ssh
    list: true
  register: ssh_dir_read

- name: Recursively read directory contents two levels deep
  o0_o.posix.read:
    path: /var/log
    children: 2
  register: log_tree_read

- name: Ask what /bin/sh really is, hop by hop
  o0_o.posix.read:
    path: /bin/sh
    resolve: true
  register: sh_resolution

- name: Read a symlink without following it
  o0_o.posix.read:
    path: /etc/localtime
    follow: false
  register: localtime_link_read

- name: Walk a symlink chain
  o0_o.posix.read:
    path: /etc/resolv.conf
    follow: recursive
  register: resolv_read

- name: Inspect multiple files at once
  o0_o.posix.read:
    paths:
      - /etc/motd
      - /etc/issue
      - /etc/hostname
  register: multi_read
"""

RETURN = r"""
paths:
  description:
    - Mapping of inspected paths to collected information.
    - When I(parents) is enabled, additional entries are included for the
      parent directories.
    - When I(follow=recursive), additional entries are included for all
      symlink targets in the resolution chain.
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
        uid:
          description: Numeric ID of the owning user
          type: int
          sample: 0
        gid:
          description: Numeric ID of the owning group
          type: int
          sample: 0
        size:
          description:
            - Size of the file in bytes, with a human readable rendering.
            - Only reported for regular files.
          type: dict
          returned: when the path is a regular file
          sample: {bytes: 1024, pretty: '1 KiB'}
        readable:
          description: Whether the path is readable for the remote user
          type: bool
          sample: true
        writable:
          description: Whether the path is writable for the remote user
          type: bool
          sample: true
        executable:
          description: Whether the path is executable for the remote user
          type: bool
          sample: true
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
        realpath:
          description:
            - The ultimate target a symbolic link resolved to.
            - The rest of the entry describes that target, not the link.
          type: str
          sample: /usr/share/zoneinfo/UTC
          returned: when I(follow=true) resolved a symlink
        resolution:
          description:
            - The chain the path resolves through, as an ordered list of
              the absolute paths the walk visited.
            - The first step is the path as it was asked for and the
              last is the canonical path it names. A path that is
              nothing but itself has a chain of one.
            - Every hop is a step, a linked directory component as much
              as a linked name, so a chain may be longer than the number
              of links at the end of the path.
            - Published whenever I(resolve=true) and the walk answered,
              whether or not I(attributes) is on.
          type: list
          elements: str
          returned: when I(resolve=true)
          sample:
            - /bin/sh
            - /usr/bin/sh
            - /usr/bin/bash
        modified:
          description: Modification time, in seconds and rendered
          type: dict
          returned: when timestamps are retrievable
          sample: {seconds: 1735689600, pretty: '2025-01-01 00:00:00 UTC'}
        changed:
          description: Inode change time, in seconds and rendered
          type: dict
          returned: when timestamps are retrievable
          sample: {seconds: 1735689600, pretty: '2025-01-01 00:00:00 UTC'}
        created:
          description: Birth time, in seconds and rendered
          type: dict
          returned: when the filesystem records a birth time
          sample: {seconds: 1735689600, pretty: '2025-01-01 00:00:00 UTC'}
        acl:
          description:
            - ACL details obtained via getfacl or derived from extended
              attributes when available.
            - A C(type) field indicates the ACL provider (for example
              C(posix), C(macos), C(nfs4)) and C(entries) lists the
              individual ACL entries.
            - POSIX default entries appear as entries with
              C(inheritance) and C(only) true, not under a separate
              key.
          type: dict
          returned: when ACL data is retrievable
          sample: {type: posix, entries: [{type: mask, read: true}]}
        xattrs:
          description:
            - Extended attributes gathered for the path, nested by the
              dotted components of each attribute name.
            - Values that do not decode as text are returned base64
              encoded.
          type: dict
          returned: when I(extended=true) and xattrs are retrievable
          sample: {user: {comment: hello}}
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
        mime:
          description: MIME type and subtype reported by the file command
          type: dict
          returned: when I(mime=true)
          sample: {type: text, subtype: plain}
        md5:
          description: MD5 checksum of the file content
          type: str
          returned: when I(md5=true) and the path is a regular file
        sha1:
          description: SHA-1 checksum of the file content
          type: str
          returned: when I(sha1=true) and the path is a regular file
        sha256:
          description: SHA-256 checksum of the file content
          type: str
          returned: when I(sha256=true) and the path is a regular file
        sha512:
          description: SHA-512 checksum of the file content
          type: str
          returned: when I(sha512=true) and the path is a regular file
        encoding:
          description:
            - Encoding used to decode the returned content.
            - C(base64) or C(hex) for content that is not text.
          type: str
          returned: when content is included
          sample: utf-8
        content:
          description:
            - Decoded file content using the reported encoding.
            - The file's bytes as they stand. A file ending in a
              newline reports that newline, and spaces at the end of
              the last line survive; nothing is trimmed on the way
              back. Code comparing this against a literal has to
              spell the terminator out.
            - Only regular files are read, so any other type is
              reported without this key.
          type: str
          returned: when I(content=true), I(lines=true), or I(encoding) is
            set, and the path is a regular file
        lines:
          description: File content split into lines, without terminators
          type: list
          elements: str
          returned: when I(lines=true), the path is a regular file, and the
            content decodes to text
        children:
          description:
            - List of child paths for directories.
            - An empty list is a directory that holds nothing. A
              directory that would not list, for want of permission
              most often, omits this key instead - a question that
              could not be asked is not an answer of none.
          type: list
          elements: str
          returned: when the path is a directory that listed and I(list)
            or I(children) is enabled
          sample: ['/etc/ssh/ssh_config', '/etc/ssh/sshd_config']
changed:
  description: Always false as this is a read-only module
  returned: always
  type: bool
  sample: false
commands:
  description: Number of commands run on the target
  returned: always
  type: int
  sample: 12
batches:
  description: Number of batches the commands were executed in
  returned: always
  type: int
  sample: 2
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
        "attributes": {"type": "bool", "default": True},
        "extended": {"type": "bool", "default": False},
        "content": {"type": "bool", "default": False},
        "lines": {"type": "bool", "default": False},
        "encoding": {"type": "str", "default": None},
        "mime": {"type": "bool", "default": False},
        "md5": {"type": "bool", "default": False},
        "sha1": {"type": "bool", "default": False},
        "sha256": {"type": "bool", "default": False},
        "sha512": {"type": "bool", "default": False},
        "parents": {"type": "raw", "default": False},
        "follow": {"type": "raw", "default": True},
        "resolve": {"type": "bool", "default": False},
        "list": {"type": "bool", "default": False},
        "children": {"type": "raw", "default": False},
        "raw": {"type": "raw", "default": "auto"},
    }

    module = AnsibleModule(
        argument_spec=argument_spec, supports_check_mode=True
    )
    module.fail_json(msg="This module must be run via its action plugin.")


if __name__ == "__main__":
    main()
