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
module: config
short_description: Ask a host for the configuration limits it answers
version_added: "2.0.0"
description:
  - Asks the host for every configuration variable IEEE Std 1003.1
    names, one C(getconf) per variable in a single batch, and returns
    what it answered.
  - This is the C(config) subset of M(o0_o.posix.facts) as a module of
    its own. Both compose through one processor, so the two publish one
    shape under one name and cannot disagree about it.
  - A variable the host has and does not limit is C(null), which is
    what C(undefined) means here. A variable the host would not answer
    for at all is left out, because a refusal and an unlimited value
    are different claims and C(null) is already spent on the second.
  - Does not require Python on the managed host.
options:
  gather:
    description:
      - Also publish the answer as facts, under
        C(ansible_facts.o0_os.config).
      - The returns are always populated; this only decides whether the
        same values are set as host facts for later tasks to read.
    type: bool
    default: false
extends_documentation_fragment:
  - o0_o.posix.evidence
author:
  - oØ.o (@o0-o)
notes:
  - This module is implemented as an action plugin and supports raw
    fallback.
  - The variables are typed the way the host printed them, an integer
    where it printed a number, so a consumer compares against a number
    rather than against a spelling of one.
  - These same variables are the C(config) evidence kind a compliance
    verdict names. A verdict is a claim about the host that a variable
    supports, so the verdict carries the variable and its value; here
    the variables are the fact, and a fact is not evidence for itself,
    which is why this namespace names the command that asked and
    nothing more.
attributes:
  check_mode:
    description: >-
      This module supports check mode. Asking a host what it limits
      changes nothing, so the answer is the same either way.
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
    description: Gather POSIX facts, the configuration among them
  - module: o0_o.posix.compliance
    description: Check the standards a host claims to support
"""

EXAMPLES = r"""
- name: Ask the host what it limits
  o0_o.posix.config:
  register: config_reg

- name: Show the longest argument list the host will take
  ansible.builtin.debug:
    var: config_reg['config']['ARG_MAX']

- name: Publish the answer as facts for later tasks
  o0_o.posix.config:
    gather: true

- name: Read a limit back off the facts
  ansible.builtin.debug:
    var: ansible_facts['o0_os']['config']['OPEN_MAX']

- name: Refuse to run where the host will not take a long argument list
  ansible.builtin.assert:
    that:
      - config_reg['config']['ARG_MAX'] > 100000
    fail_msg: >-
      This host takes only {{ config_reg['config']['ARG_MAX'] }} bytes
      of arguments

- name: Tell a variable the host does not limit from one it will not say
  ansible.builtin.debug:
    msg: >-
      SYMLOOP_MAX is
      {{ 'unlimited' if config_reg['config']['SYMLOOP_MAX'] is none
         else config_reg['config']['SYMLOOP_MAX'] }}
  when: "'SYMLOOP_MAX' in config_reg['config']"
"""

RETURN = r"""
config:
  description:
    - The configuration variables the host answered for, keyed by the
      name C(getconf) knows them by.
    - Each value is typed the way the host printed it - an integer
      where it printed a number, a string where it printed a path.
    - C(null) is a variable the host has and does not limit, which is
      what C(undefined) means. A variable the host would not answer
      for is absent instead, because a refusal is a different claim.
    - Empty where the host answered for nothing, which is a host that
      was asked rather than one that was not.
  returned: always
  type: dict
  sample:
    ARG_MAX: 1048576
    OPEN_MAX: 1024
    PATH: /usr/bin:/bin
    _POSIX_VERSION: 200809
evidence:
  description:
    - What was consulted, in the collection's one provenance
      vocabulary. One command and nothing else.
    - No C(config) kind here. These variables are the fact rather than
      evidence for one, and a fact is not evidence for itself; a
      compliance verdict carries the variables it rests on because the
      verdict is a claim they support.
  returned: always
  type: dict
  sample:
    commands:
      - getconf
ansible_facts:
  description:
    - The same answer as host facts, under C(o0_os.config), with the
      C(evidence) and C(origins) the facts module publishes beside it.
  returned: when I(gather=true) and the host answered
  type: dict
  sample:
    o0_os:
      config:
        ARG_MAX: 1048576
      evidence:
        commands:
          - getconf
      origins:
        - o0_o.posix.config
changed:
  description: Always false; asking a host what it limits changes nothing
  returned: always
  type: bool
  sample: false
"""
from ansible.module_utils.basic import AnsibleModule


def main() -> None:
    """Fail if this module is run directly without the action plugin."""

    argument_spec = {"gather": {"type": "bool", "default": False}}

    module = AnsibleModule(
        argument_spec=argument_spec, supports_check_mode=True
    )
    module.fail_json(msg="This module must be run via its action plugin.")


if __name__ == "__main__":
    main()
