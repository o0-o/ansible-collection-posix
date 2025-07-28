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
#   - The command module in Ansible core (GPL-3.0-or-later)
#     https://github.com/ansible/ansible/blob/fcffd707c6f8d959d7dc7c6e7a91fa2f59fd0308/lib/ansible/modules/command.py
#
# This file is part of the o0_o.posix Ansible Collection.

from __future__ import absolute_import, division, print_function
__metaclass__ = type


DOCUMENTATION = r'''
---
module: command
short_description: Execute commands on remote hosts with fallback support
version_added: '1.0.0'
description:
  - This module executes commands on remote hosts using the built-in
    C(ansible.builtin.command) module.
  - If a Python interpreter is unavailable, it automatically falls back to raw
    POSIX-compatible execution using C(sh) or C(cat).
  - Supports check mode and idempotence using C(creates)/C(removes).
options:
  cmd:
    description:
      - The command to run on the remote node.
      - Only one of C(cmd) or C(argv) may be specified.
    required: false
    type: str
  argv:
    description:
      - A list of command arguments to run. Cannot be used with C(cmd).
    required: false
    type: list
    elements: str
  chdir:
    description:
      - Change into this directory on the remote node before running the
        command.
    type: path
  executable:
    description:
      - The executable to use to run the command.
      - Only used when C(_uses_shell=true).
    type: str
  _uses_shell:
    description:
      - If true, the command will be executed through the shell
        (e.g. C(sh -c "...")).
      - This enables variable expansion and complex expressions.
    type: bool
    default: false
  expand_argument_vars:
    description:
      - Whether to expand shell variables inside arguments.
      - Must match the value of C(_uses_shell) for raw fallback to work.
    type: bool
  creates:
    description:
      - If the specified path exists, the command will not be run.
    type: path
  removes:
    description:
      - If the specified path does not exist, the command will not be run.
    type: path
  stdin:
    description:
      - The string to pass on stdin before running the command.
    type: str
  stdin_add_newline:
    description:
      - If true and C(stdin) is set, append a newline to stdin if not already
        present.
    type: bool
    default: true
  strip_empty_ends:
    description:
      - Strip empty newlines from the end of stdout/stderr.
    type: bool
    default: true
  _force_raw:
    description:
      - Internal flag to bypass the builtin module and force raw command
        fallback.
      - Useful for debugging, testing, or bootstrap scenarios.
    type: bool
    default: false
extends_documentation_fragment:
  - action_common_attributes
  - o0_o.posix.raw_fallback
attributes:
  check_mode:
    support: full
    description:
      - This module fully supports check mode. It simulates command execution
        without making changes.
  diff_mode:
    support: none
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

author:
  - oØ.o (@o0-o)
seealso:
  - module: ansible.builtin.command
notes:
  - Only one of C(cmd) or C(argv) may be used; supplying both will cause an
    error.
  - When C(_force_raw=true), all execution is performed via raw shell
    invocation, bypassing the builtin command module entirely.
  - The C(executable) parameter is only supported when C(_uses_shell=true), and
    is ignored during raw fallback.
  - Variable expansion is only supported when C(_uses_shell=true and
    expand_argument_vars=true); these two options must match in raw mode.
  - In raw fallback mode, certain behaviors such as complex shell expressions
    or non-standard quoting may differ from Python-based execution.
  - The raw fallback does not support parameter substitution or environment
    variables in the same way as the builtin module.
'''

EXAMPLES = r'''
- name: Run a simple command using argv
  o0_o.posix.command:
    argv: ['ls', '-l', '/etc']

- name: Run a command using shell expression
  o0_o.posix.command:
    cmd: echo "Hello $USER"
    _uses_shell: true
    expand_argument_vars: true

- name: Skip command if file already exists
  o0_o.posix.command:
    argv: ['echo', 'Hello world']
    creates: /tmp/already_exists.txt

- name: Force raw fallback (bypassing builtin command)
  o0_o.posix.command:
    argv: ['uptime']
    _force_raw: true
'''

RETURN = r'''
msg:
  description: Human-readable message about the task result.
  type: str
  returned: always
start:
  description: Timestamp of when the command started.
  type: str
  returned: when supported
end:
  description: Timestamp of when the command ended.
  type: str
  returned: when supported
delta:
  description: Time taken to execute the command.
  type: str
  returned: when supported
stdout:
  description: The standard output from the command.
  type: str
  returned: always
stderr:
  description: The standard error from the command.
  type: str
  returned: always
cmd:
  description: The command that was executed.
  type: list
  elements: str
  returned: always
rc:
  description: The return code of the command.
  type: int
  returned: always
raw:
  description: Whether raw fallback mode was used instead of builtin.
  type: bool
  returned: always
stdout_lines:
  description: The command standard output split in lines.
  returned: always
  type: list
stderr_lines:
  description: The command standard error split in lines.
  returned: always
  type: list
'''


from ansible.module_utils.basic import AnsibleModule


def main():
    # This module is used only to support documentation and validation.
    module = AnsibleModule(
        argument_spec={
            '_uses_shell': {'type': 'bool', 'default': False},
            'cmd': {},
            'argv': {'type': 'list', 'elements': 'str'},
            'chdir': {'type': 'path'},
            'executable': {},
            'expand_argument_vars': {'type': 'bool'},
            'creates': {'type': 'path'},
            'removes': {'type': 'path'},
            'stdin': {'required': False},
            'stdin_add_newline': {'type': 'bool', 'default': True},
            'strip_empty_ends': {'type': 'bool', 'default': True},
            '_force_raw': {'type': 'bool', 'default': False},
        },
        supports_check_mode=True,
    )
    module.fail_json(msg='This module must be run via its action plugin.')


if __name__ == '__main__':
    main()
