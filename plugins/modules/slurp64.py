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
module: slurp64
short_description: Read a remote file with decoding and raw fallback for
  minimal systems
version_added: "1.0.0"
description:
  - Reads the content of a file from the remote system.
  - Attempts to use C(ansible.builtin.slurp) when a Python interpreter is
    available.
  - Falls back to a raw C(cat) command if Python is missing.
  - Content is always automatically base64-decoded and UTF-8 decoded
    before being returned, regardless of execution.
  - Designed for compatibility with minimal or bootstrapping environments.
options:
  src:
    description:
      - Full path to the file to read on the remote system.
    required: true
    type: str
extends_documentation_fragment:
  - action_common_attributes
  - o0_o.posix.raw_fallback
attributes:
  check_mode:
    support: full
    description:
      - This module fully supports check mode. It simulates command execution without making changes.
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
  - module: ansible.builtin.slurp
notes:
  - This module must be invoked via its action plugin.
  - If Python is unavailable on the remote host, raw fallback will be used
    automatically.
'''

EXAMPLES = r'''
- name: Read a file using slurp64
  o0_o.posix.slurp64:
    src: /etc/hostname

- name: Force raw fallback mode for debugging
  o0_o.posix.slurp64:
    src: /etc/hostname
    _force_raw: true
'''

RETURN = r'''
content:
  description: UTF-8-decoded content of the file.
  type: str
  returned: success
raw:
  description: Whether the raw fallback mechanism was used.
  type: bool
  returned: always
source:
  description: Path to the file that was read.
  type: str
  returned: always
'''


from ansible.module_utils.basic import AnsibleModule


def main():
    module = AnsibleModule(
        argument_spec=dict(
            src=dict(type='str', required=True),
            _force_raw=dict(type='bool', default=False),
        ),
        supports_check_mode=True,
    )
    module.fail_json(msg="This module must be run via its action plugin.")


if __name__ == '__main__':
    main()
