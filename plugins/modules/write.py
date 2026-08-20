# vim: ts=4:sw=4:sts=4:et:ft=python
# -*- mode: python; tab-width: 4; indent-tabs-mode: nil; -*-
#
# GNU General Public License v3.0+
# SPDX-License-Identifier: GPL-3.0-or-later
# (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
#
# Copyright (c) 2025 oØ.o (@o0-o)
#
# Adapted from:
#   - The template and lineinfile_dedupe modules in this collection,
#     themselves adapted from Ansible core's template action plugin and
#     lineinfile module (GPL-3.0-or-later)
#
# This file is part of the o0_o.posix Ansible Collection.

from __future__ import absolute_import, division, print_function
from __future__ import annotations

DOCUMENTATION = r"""
---
module: write
short_description: Write files on POSIX hosts with raw fallback
version_added: '2.0.0'
description:
  - Writes a file on the remote host, generalized over every source its
    contents can have, and over the bare states a path can be left in.
  - The argument present in the task selects the operation. At most one
    of C(content), C(src), C(template), C(line), or C(block) may be
    given; they are mutually exclusive. A task naming none of them must
    select a bare file state with C(state) set to C(absent),
    C(directory), C(touch), or C(link).
  - 'C(content): write a literal string.'
  - 'C(src): copy a file from the controller, or from the remote host
    when C(remote_src=true).'
  - 'C(template): render a Jinja2 template on the controller and write
    the result.'
  - 'C(line): ensure a single line is present or absent, deduplicating
    other matching lines by default.'
  - 'C(block): ensure a marked block is present or absent.'
  - The C(content), C(src), and C(template) families require
    C(state=present). The C(line) and C(block) families accept
    C(state=present) or C(state=absent).
  - Every family falls back to raw POSIX shell commands when the target
    has no usable Python interpreter.
  - Ignores C(unsafe_writes) by design.
options:
  dest:
    description:
      - Path on the remote host to write, edit, or bring to a state.
      - Parent directories are created as needed for the families that
        write content.
    type: path
    required: true
    aliases: [path, name]
  state:
    description:
      - Whether the destination should be present or absent, and which
        bare file state to apply when no family argument is given.
      - C(present) is the only state the C(content), C(src), and
        C(template) families accept.
      - C(absent) removes the destination when no family argument is
        given, or removes the matching lines or block when C(line) or
        C(block) is given. Removing from a file that does not exist
        reports no change.
      - C(directory), C(touch), and C(link) are bare states and cannot
        be combined with a family argument.
      - C(touch) asserts that the destination exists and nothing more.
        An absent path is created and the task reports changed; an
        existing path is left exactly as it is, with no C(touch) run
        against it and no timestamp rewritten, and the task reports no
        change. Ownership and mode given alongside the state are
        enforced either way.
      - That timestamp behavior is a deliberate divergence from
        M(ansible.builtin.file), whose C(touch) state defaults
        C(modification_time) and C(access_time) to C(now) and so
        rewrites both stamps and reports changed on every run. Use
        M(ansible.builtin.file) or M(ansible.builtin.command) when
        bumping a timestamp is the point.
    type: str
    choices: [present, absent, directory, touch, link]
    default: present
  content:
    description:
      - Literal content to write to C(dest).
      - Selects the content family. Mutually exclusive with C(src),
        C(template), C(line), and C(block).
    type: str
  src:
    description:
      - Path to the file to copy to C(dest).
      - Interpreted on the controller and resolved through the usual
        C(files/) search path, or on the remote host when
        C(remote_src=true).
      - Selects the copy family. Mutually exclusive with C(content),
        C(template), C(line), and C(block).
    type: path
  template:
    description:
      - Path to the Jinja2 template to render.
      - Interpreted on the controller and resolved through the usual
        C(templates/) search path.
      - Selects the template family. Mutually exclusive with
        C(content), C(src), C(line), and C(block).
    type: path
  line:
    description:
      - The line to insert, or to match when C(state=absent).
      - Selects the line family. Mutually exclusive with C(content),
        C(src), C(template), and C(block).
    type: str
    aliases: [value]
  block:
    description:
      - The text to insert between the block markers.
      - Selects the block family. Mutually exclusive with C(content),
        C(src), C(template), and C(line).
    type: str
  remote_src:
    description:
      - Read C(src) from the remote host instead of the controller.
      - Only meaningful for the copy family.
    type: bool
    default: false
  force:
    description:
      - Overwrite a destination that already exists. Applies to the
        C(content), C(src), and C(template) families only.
      - When C(false), an existing destination is left untouched and
        the task reports no change.
    type: bool
    default: true
  block_start_string:
    description:
      - The string marking the beginning of a template block.
      - Only meaningful for the template family.
    type: str
    default: '{%'
  block_end_string:
    description:
      - The string marking the end of a template block.
      - Only meaningful for the template family.
    type: str
    default: '%}'
  variable_start_string:
    description:
      - The string marking the beginning of a print statement.
      - Only meaningful for the template family.
    type: str
    default: '{{'
  variable_end_string:
    description:
      - The string marking the end of a print statement.
      - Only meaningful for the template family.
    type: str
    default: '}}'
  comment_start_string:
    description:
      - The string marking the beginning of a template comment.
      - Only meaningful for the template family.
    type: str
    default: '{#'
  comment_end_string:
    description:
      - The string marking the end of a template comment.
      - Only meaningful for the template family.
    type: str
    default: '#}'
  trim_blocks:
    description:
      - Remove the first newline after a template block.
      - Only meaningful for the template family.
    type: bool
    default: true
  lstrip_blocks:
    description:
      - Strip leading spaces and tabs from the start of a line to a
        template block.
      - Only meaningful for the template family.
    type: bool
    default: false
  newline_sequence:
    description:
      - Sequence used to terminate lines in the rendered output.
      - Only meaningful for the template family.
    type: str
    choices: ["\n", "\r", "\r\n"]
    default: "\n"
  regexp:
    description:
      - Regular expression matching the lines to replace or remove.
      - Only meaningful for the line family. Mutually exclusive with
        C(search_string).
    type: str
    aliases: [regex]
  search_string:
    description:
      - Literal string matching the lines to replace or remove.
      - Only meaningful for the line family. Mutually exclusive with
        C(regexp) and with C(backrefs).
    type: str
  insertafter:
    description:
      - Insert after the last line matching this expression, or at the
        end of the file with the special token C(EOF).
      - Only meaningful for the line and block families. Mutually
        exclusive with C(insertbefore).
    type: str
  insertbefore:
    description:
      - Insert before the last line matching this expression, or at the
        start of the file with the special token C(BOF).
      - Only meaningful for the line and block families. Mutually
        exclusive with C(insertafter).
    type: str
  firstmatch:
    description:
      - Insert relative to the first line matching C(insertafter) or
        C(insertbefore) rather than the last.
      - Only meaningful for the line family.
    type: bool
    default: false
  backrefs:
    description:
      - Expand backreferences from C(regexp) in C(line).
      - Requires C(regexp). Only meaningful for the line family.
    type: bool
    default: false
  dedupe:
    description:
      - Remove matching duplicates beyond the selected instance.
      - Only meaningful for the line family.
    type: bool
    default: true
  marker:
    description:
      - The marker line template. C({mark}) is replaced with
        C(marker_begin) and C(marker_end).
      - Only meaningful for the block family.
    type: str
    default: '# {mark} ANSIBLE MANAGED BLOCK'
  marker_begin:
    description:
      - The text substituted for C({mark}) in the opening marker.
      - Only meaningful for the block family.
    type: str
    default: BEGIN
  marker_end:
    description:
      - The text substituted for C({mark}) in the closing marker.
      - Only meaningful for the block family.
    type: str
    default: END
  create:
    description:
      - Create C(dest) if it does not exist.
      - Only meaningful for the line and block families; the other
        families always create the destination.
    type: bool
    default: false
  target:
    description:
      - The path the symbolic link points at.
      - Required when C(state=link).
    type: path
  raw:
    description:
      - Control raw execution mode behavior.
      - 'C(true): Force raw fallback mode, bypassing native Python.'
      - 'C(false): Force native Python execution (fail if unavailable).'
      - 'C("auto"): Automatically detect and use the best method.'
      - Useful for debugging, testing, or bootstrap scenarios.
    type: raw
    default: "auto"
extends_documentation_fragment:
  - action_common_attributes
  - o0_o.posix.file
attributes:
  check_mode:
    support: full
    description:
      - This module fully supports check mode. It reports the change it
        would make without touching the destination.
  diff_mode:
    support: full
    description:
      - This module returns a unified diff of the destination before
        and after the write.
  async:
    support: none
    description:
      - This module does not support asynchronous execution.
  platform:
    platforms: posix
    description:
      - Only supported on POSIX-compatible systems.
  safe_file_operations:
    support: full
    description:
      - This module fully supports safe file operations.
author:
  - oØ.o (@o0-o)
seealso:
  - module: ansible.builtin.copy
  - module: ansible.builtin.template
  - module: ansible.builtin.file
  - module: ansible.builtin.lineinfile
  - module: ansible.builtin.blockinfile
  - module: o0_o.posix.read
    description: Inspect file metadata and content
notes:
  - This module must be invoked via its action plugin.
  - At most one of C(content), C(src), C(template), C(line), or C(block)
    may be supplied; they are mutually exclusive.
  - C(insertafter) and C(insertbefore) are mutually exclusive, as are
    C(regexp) and C(search_string), and C(backrefs) and
    C(search_string).
  - Every family supports raw fallback for hosts without a usable
    Python interpreter; C(raw=true) forces it.
  - Binary sources are not supported. A controller-side C(src) that is
    not valid UTF-8 text fails, as does a remote source that reads back
    as base64 or hex.
  - C(mode=preserve) is only supported for a controller-side C(src) and
    for C(template). It fails with C(remote_src=true) and has no
    meaning for the other families.
  - C(state=link) requires C(target).
  - The C(unsafe_writes) option is intentionally not supported.
"""

EXAMPLES = r"""
- name: Write literal content
  o0_o.posix.write:
    dest: /etc/motd
    content: |
      Managed by Ansible.
    owner: root
    group: wheel
    mode: '0644'

- name: Copy a file from the controller
  o0_o.posix.write:
    src: sshd_config
    dest: /etc/ssh/sshd_config
    mode: preserve
    backup: true
    validate: /usr/sbin/sshd -t -f %s

- name: Copy a file already on the remote host
  o0_o.posix.write:
    src: /etc/skel/.profile
    dest: /home/deploy/.profile
    remote_src: true
    owner: deploy

- name: Render a template
  o0_o.posix.write:
    template: nginx.conf.j2
    dest: /etc/nginx/nginx.conf
    mode: '0644'
    validate: nginx -t -c %s

- name: Ensure a line is present, deduplicating the rest
  o0_o.posix.write:
    dest: /etc/ssh/sshd_config
    line: 'PermitRootLogin no'
    regexp: '^#?\s*PermitRootLogin'
    dedupe: true
    create: true

- name: Ensure a marked block is present
  o0_o.posix.write:
    dest: /etc/hosts
    block: |
      10.0.0.10 db
      10.0.0.11 cache
    marker: '# {mark} INVENTORY HOSTS'
    insertafter: EOF

- name: Ensure a directory exists
  o0_o.posix.write:
    dest: /srv/app
    state: directory
    owner: app
    mode: '0755'

- name: Ensure a symbolic link exists
  o0_o.posix.write:
    dest: /etc/localtime
    target: /usr/share/zoneinfo/UTC
    state: link

- name: Ensure a file exists
  o0_o.posix.write:
    dest: /var/log/app.log
    state: touch
    owner: app
    mode: '0640'

- name: Ensure a path is absent
  o0_o.posix.write:
    dest: /etc/motd.old
    state: absent

- name: Force raw fallback
  o0_o.posix.write:
    dest: /tmp/bootstrap.txt
    content: 'no python here'
    raw: true
"""

RETURN = r"""
changed:
  description: Whether the destination was modified.
  type: bool
  returned: always
msg:
  description: Description of the operation performed.
  type: str
  returned: always
  sample: File written successfully
raw:
  description: Whether raw fallback mode was used instead of Python.
  type: bool
  returned: always
backup_file:
  description:
    - Path of the backup copy created before writing.
    - Named for the destination, a digest of its path, and a UTC
      timestamp.
  type: str
  returned: >-
    when backup is true, the destination changed, and check mode is
    off
  sample: /etc/motd.d41d8cd98f00b204e9800998ecf8427e.20250101120000
diff:
  description:
    - Before and after content of the destination.
    - Contains the C(before), C(after), C(before_header),
      C(after_header), and C(unified_diff) keys.
  type: dict
  returned: in diff mode, when the destination changed
found:
  description: Number of lines removed by the line family.
  type: int
  returned: when line is given with state=absent
  sample: 2
rc:
  description: Return code of the write, C(0) on success.
  type: int
  returned: when a content, copy, template, line, or block family ran
  sample: 0
"""

from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils.common.file import get_file_arg_spec


def main() -> None:
    """Fail if this module is run directly without the action plugin."""

    argument_spec = get_file_arg_spec()
    argument_spec.pop("attributes")
    argument_spec.update(
        {
            "dest": {
                "type": "path",
                "required": True,
                "aliases": ["path", "name"],
            },
            "state": {
                "type": "str",
                "choices": [
                    "present",
                    "absent",
                    "directory",
                    "touch",
                    "link",
                ],
                "default": "present",
            },
            # Family canaries: exactly one selects the operation
            "content": {"type": "str", "no_log": False},
            "src": {"type": "path"},
            "template": {"type": "path"},
            "line": {"type": "str", "aliases": ["value"]},
            "block": {"type": "str"},
            # Copy family
            "remote_src": {"type": "bool", "default": False},
            "force": {"type": "bool", "default": True},
            # Template family
            "block_start_string": {"type": "str", "default": "{%"},
            "block_end_string": {"type": "str", "default": "%}"},
            "variable_start_string": {"type": "str", "default": "{{"},
            "variable_end_string": {"type": "str", "default": "}}"},
            "comment_start_string": {"type": "str", "default": "{#"},
            "comment_end_string": {"type": "str", "default": "#}"},
            "trim_blocks": {"type": "bool", "default": True},
            "lstrip_blocks": {"type": "bool", "default": False},
            "newline_sequence": {
                "type": "str",
                "choices": ["\n", "\r", "\r\n"],
                "default": "\n",
            },
            # Line family
            "regexp": {"type": "str", "aliases": ["regex"]},
            "search_string": {"type": "str"},
            "insertafter": {"type": "str"},
            "insertbefore": {"type": "str"},
            "firstmatch": {"type": "bool", "default": False},
            "backrefs": {"type": "bool", "default": False},
            "dedupe": {"type": "bool", "default": True},
            # Block family
            "marker": {
                "type": "str",
                "default": "# {mark} ANSIBLE MANAGED BLOCK",
            },
            "marker_begin": {"type": "str", "default": "BEGIN"},
            "marker_end": {"type": "str", "default": "END"},
            # Line and block families
            "create": {"type": "bool", "default": False},
            # Link family
            "target": {"type": "path"},
            # Shared
            "backup": {"type": "bool", "default": False},
            "validate": {"type": "str"},
            "raw": {"type": "raw", "default": "auto"},
        }
    )

    module = AnsibleModule(
        argument_spec=argument_spec, supports_check_mode=True
    )
    module.fail_json(msg="This module must be run via its action plugin.")


if __name__ == "__main__":
    main()
