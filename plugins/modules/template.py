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

DOCUMENTATION = r'''
---
module: template
short_description: Template a file out to a target host witih raw fallback
  support
version_added: "1.2.0"
description:
  - Renders a Jinja2 template on the controller and transfers the result to
    the remote host.
  - Uses POSIX-safe fallback if Python is unavailable.
  - Ignores C(unsafe_writes) by design.
  - Templates are processed by the L(Jinja2 templating
    language,https://jinja.palletsprojects.com/en/stable/).
  - Documentation on the template formatting can be found in the
    L(Template Designer
    Documentation,https://jinja.palletsprojects.com/en/stable/templates/).
  - Additional variables listed below can be used in templates.
  - C(ansible_managed) (configurable via the C(defaults) section of
    C(ansible.cfg)) contains a string which can be used to
    describe the template name, host, modification time of the template file
    and the owner uid.
  - C(template_host) contains the node name of the template's machine.
  - C(template_uid) is the numeric user id of the owner.
  - C(template_path) is the path of the template.
  - C(template_fullpath) is the absolute path of the template.
  - C(template_destpath) is the path of the template on the remote system
    (added in 2.8).
  - C(template_run_date) is the date that the template was rendered.
  - 'Unlike M(ansible.builtin.template), this module:'
  - ' - Always follows symbolic links (C(follow=true))'
  - ' - Ignores C(unsafe_writes) for safety'
  - ' - Always uses C(utf-8) encoding'
options:
  src:
    description:
      - Path to the local Jinja2 template.
      - Relative paths are interpreted relative to the role or playbook.
    type: path
    required: true
  dest:
    description:
      - Absolute path on the remote host to write the rendered file to.
    type: path
    required: true
  block_start_string:
    description:
      - The string marking the beginning of a block.
    type: str
    default: "{%"
  block_end_string:
    description:
      - The string marking the end of a block.
    type: str
    default: "%}"
  force:
    description:
      - Force indicates that an existing file should be overwritten on change.
    type: bool
    default: true
  variable_start_string:
    description:
      - The string marking the beginning of a print statement.
    type: str
    default: "{{"
  variable_end_string:
    description:
      - The string marking the end of a print statement.
    type: str
    default: "}}"
  comment_start_string:
    description:
      - The string marking the beginning of a comment.
    type: str
    default: "{#"
  comment_end_string:
    description:
      - The string marking the end of a comment.
    type: str
    default: "#}"
  trim_blocks:
    description:
      - If this is set to C(True), the first newline after a block is removed.
    type: bool
    default: true
  lstrip_blocks:
    description:
      - If this is set to C(True), leading spaces and tabs are stripped from
        the start of a line to a block.
    type: bool
    default: false
  newline_sequence:
    description:
      - Sequence used to terminate lines in the rendered output.
    type: str
    choices: ["\n", "\r", "\r\n"]
    default: "\n"
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
  - module: ansible.builtin.template
notes:
  - This module must be invoked via its action plugin.
  - This implementation always follows symlinks (C(follow=true)).
  - Does not support C(unsafe_writes).
  - Template output is always written using UTF-8 encoding.
'''

EXAMPLES = r'''
- name: Render a config file from template
  o0_o.posix.template:
    src: nginx.conf.j2
    dest: /etc/nginx/nginx.conf
    mode: '0644'
    owner: root
    group: root
    validate: nginx -t -c %s

- name: Use raw fallback explicitly
  o0_o.posix.template:
    src: foo.j2
    dest: /tmp/foo.txt
    _force_raw: true
'''

RETURN = r'''
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
'''

from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils.common.file import get_file_arg_spec


def main():
    argument_spec = get_file_arg_spec()
    argument_spec.pop('attributes')
    argument_spec.update(dict(
        block_end_string=dict(
            type='str',
            default='%}',
        ),
        block_start_string=dict(
            type='str',
            default='{%'
        ),
        comment_end_string=dict(
            type='str',
            default='#}',
        ),
        comment_start_string=dict(
            type='str',
            default='{#',
        ),
        dest=dict(type='path', required=True),
        force=dict(type='bool', default=True),
        lstrip_blocks=dict(type='bool', default=False),
        newline_sequence=dict(
            type='str',
            choices=['\n', '\r', '\r\n'],
            default='\n',
        ),
        src=dict(type='path', required=True),
        trim_blocks=dict(type='bool', default=True),
        backup=dict(type='bool', default=False),
        validate=dict(type='str'),
        variable_end_string=dict(
            type='str',
            default='}}',
        ),
        variable_start_string=dict(
            type='str',
            default='{{',
        ),
        _force_raw=dict(type='bool', default=False),
    ))

    module = AnsibleModule(
        argument_spec=argument_spec,
        supports_check_mode=True
    )

    module.fail_json(msg="This module must be run via its action plugin.")


if __name__ == '__main__':
    main()
