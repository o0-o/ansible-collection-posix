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
module: env
short_description: Collect POSIX environment variables
version_added: "2.0.0"
description:
  - Collects specific environment variables from the target host.
  - Runs C(printf '%s' "$VAR") per variable using C(set -eu) so that
    unset variables are distinguished from empty ones.
  - Only queries the variables you request — never captures the full
    environment, avoiding accidental exposure of secrets.
  - Does not require Python on the target host.
options:
  env:
    description:
      - One or more environment variable names to collect.
    type: list
    elements: str
    required: true
  wantlist:
    description:
      - When C(true), return a list of single-key dictionaries
        instead of a flat dictionary.
      - Useful when downstream processing expects a list of
        key/value pairs.
    type: bool
    default: false
  undefined:
    description:
      - How to handle undefined (unset) environment variables.
      - C(exclude) omits unset variables from the output.
      - C(null) includes them with a C(null) value.
    type: str
    choices: [exclude, 'null']
    default: exclude
author:
  - oØ.o (@o0-o)
notes:
  - Variables set to an empty string return C(""), which is
    distinct from unset (excluded or C(null) per the
    I(undefined) option).
  - This module is implemented as an action plugin and supports
    raw fallback.
attributes:
  check_mode:
    description: >-
      This module supports check mode. Environment variables are
      read-only so behavior is identical.
    support: full
  async:
    description: This module does not support async operation.
    support: none
  platform:
    description: Only POSIX platforms are supported.
    support: full
    platforms: posix
seealso:
  - module: o0_o.posix.facts
    description: Gather comprehensive POSIX facts
  - module: o0_o.posix.locale
    description: Detect system locale
"""

EXAMPLES = r"""
- name: Get the TZ variable
  o0_o.posix.env:
    env: TZ
  register: tz_reg

- name: Show timezone
  ansible.builtin.debug:
    var: tz_reg['env']['TZ']

- name: Collect several POSIX variables
  o0_o.posix.env:
    env:
      - HOME
      - SHELL
      - LANG
      - TZ
      - PATH
  register: posix_env_reg

- name: Show all collected variables
  ansible.builtin.debug:
    var: posix_env_reg['env']

- name: Collect as list of key/value pairs
  o0_o.posix.env:
    env:
      - HOME
      - SHELL
    wantlist: true
  register: env_list_reg

- name: Show list format
  ansible.builtin.debug:
    var: env_list_reg['env']
  # [{"HOME": "/root"}, {"SHELL": "/bin/sh"}]
"""

RETURN = r"""
env:
  description: >-
    Collected environment variables. By default a dictionary mapping
    variable names to values. Unset variables are excluded by
    default or set to C(null) when I(undefined=null). When
    I(wantlist=true), a list of single-key dictionaries.
  returned: always
  type: raw
  sample:
    HOME: /root
    SHELL: /bin/sh
    TZ: America/New_York
changed:
  description: Always false as this is a read-only module
  returned: always
  type: bool
  sample: false
msg:
  description: Summary message
  returned: always
  type: str
  sample: "Collected 4 environment variable(s)"
"""

from ansible.module_utils.basic import AnsibleModule


def main() -> None:
    """Fail if this module is run directly without the action plugin."""
    argument_spec = {
        "env": {
            "type": "list",
            "elements": "str",
            "required": True,
        },
        "wantlist": {
            "type": "bool",
            "default": False,
        },
        "undefined": {
            "type": "str",
            "choices": ["exclude", "null"],
            "default": "exclude",
        },
    }

    module = AnsibleModule(
        argument_spec=argument_spec, supports_check_mode=True
    )
    module.fail_json(msg="This module must be run via its action plugin.")


if __name__ == "__main__":
    main()
