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
#   - The lineinfile module in Ansible core (GPL-3.0-or-later)
#     https://github.com/ansible/ansible/blob/da6735160db41b7b31d34b5f46f17952592fac7f/lib/ansible/modules/lineinfile.py
#
# This file is part of the o0_o.posix Ansible Collection.

from __future__ import absolute_import, division, print_function

__metaclass__ = type


DOCUMENTATION = r"""
---
module: lineinfile_dedupe
short_description: Manage lines in text files with deduplication and raw
  fallback support
version_added: '1.1.0'
description:
  - Ensures a line is present or absent in a file.
  - Supports literal, regex, and string matching.
  - Can insert relative to patterns or at BOF/EOF.
  - Deduplicates matching lines.
  - Uses POSIX-safe fallback if Python is unavailable.
  - Ignores C(unsafe_writes) by design.
options:
  path:
    description:
      - Path to the file to operate on.
    required: true
    type: path
    aliases: [dest, destfile, name]
  regexp:
    description:
      - Regular expression to match existing lines.
    type: str
    aliases: [regex]
  search_string:
    description:
      - String to match lines (non-regex).
    type: str
  state:
    description:
      - Whether the line should be present or absent.
    type: str
    choices: [present, absent]
    default: present
  line:
    description:
      - The line to insert or match for removal.
    type: str
    aliases: [value]
  backrefs:
    description:
      - When used with C(regexp), expand backreferences in C(line).
    type: bool
    default: false
  insertafter:
    description:
      - Insert after this pattern or special token (BOF/EOF).
    type: str
  insertbefore:
    description:
      - Insert before this pattern or special token (BOF).
    type: str
  create:
    description:
      - Create the file if it does not exist.
    type: bool
    default: false
  firstmatch:
    description:
      - Use the first match found for relative insertion.
    type: bool
    default: false
  dedupe:
    description:
      - Remove matching duplicates beyond the selected instance.
    type: bool
    default: true
  _force_raw:
    description:
      - Force raw fallback mode (for testing/debugging).
    type: bool
    default: false
extends_documentation_fragment:
  - action_common_attributes
  - o0_o.posix.raw_fallback
  - o0_o.posix.file
attributes:
  check_mode:
    support: full
    description:
      - This module fully supports check mode. It simulates command execution
        without making changes.
  diff_mode:
    support: full
    description:
      - This module does not produce diff output.
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
  - module: ansible.builtin.lineinfile
notes:
  - This module must be invoked via its action plugin.
  - The C(unsafe_writes) option is intentionally not supported.
  - The line will always be inserted at the relative position if not already
    present there.
"""

EXAMPLES = r"""
- name: Ensure a line is present with deduplication
  o0_o.posix.lineinfile_dedupe:
    path: /etc/myapp.conf
    line: 'loglevel = DEBUG'
    regexp: '^loglevel\s*='
    create: true

- name: Remove matching lines
  o0_o.posix.lineinfile_dedupe:
    path: /etc/myapp.conf
    regexp: '^loglevel\s*='
    state: absent

- name: Insert line after a comment section
  o0_o.posix.lineinfile_dedupe:
    path: /etc/myapp.conf
    line: 'enabled = true'
    insertafter: '^# Enable logging'
    create: true
"""

RETURN = r"""
changed:
  description: Whether the file was modified.
  type: bool
  returned: always
msg:
  description: Description of the operation performed.
  type: str
  returned: always
backup_file:
  description: Name of the backup file created, if any.
  type: str
  returned: when backup is true
raw:
  description: Whether raw fallback mode was used.
  type: bool
  returned: always
diff:
  description: Diff of before and after file content (if diff enabled).
  type: dict
  returned: when supported
"""

from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils.common.file import get_file_arg_spec


def main():
    """Fail if this module is run directly without the action plugin."""
    argument_spec = get_file_arg_spec()
    argument_spec.pop("attributes")
    argument_spec.update(
        {
            "path": {
                "type": "path",
                "required": True,
                "aliases": ["dest", "destfile", "name"],
            },
            "regexp": {"type": "str", "aliases": ["regex"]},
            "search_string": {"type": "str"},
            "state": {
                "type": "str",
                "choices": ["absent", "present"],
                "default": "present",
            },
            "line": {"type": "str", "aliases": ["value"]},
            "backrefs": {"type": "bool", "default": False},
            "insertafter": {"type": "str"},
            "insertbefore": {"type": "str"},
            "create": {"type": "bool", "default": False},
            "backup": {"type": "bool", "default": False},
            "firstmatch": {"type": "bool", "default": False},
            "dedupe": {"type": "bool", "default": True},
            "validate": {"type": "str"},
            "_force_raw": {"type": "bool", "default": False},
        }
    )

    module = AnsibleModule(
        argument_spec=argument_spec, supports_check_mode=True
    )

    module.fail_json(msg="This module must be run via its action plugin.")


if __name__ == "__main__":
    main()
