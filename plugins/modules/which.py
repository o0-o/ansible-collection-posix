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
module: which
short_description: Resolve a command's full path on POSIX systems
version_added: "2.0.0"
description:
  - Resolves the full path to a command by clearing aliases and using
    C(command -v) with a fallback to C(which).
  - Returns command as-is for shell built-ins
  - Always executes in a POSIX shell to guarantee alias removal.
  - A resolution is a fact about the file it landed on, so it is also
    answered as an C(o0_paths) observation keyed by that path, the
    same store M(o0_o.posix.compliance) and M(o0_o.posix.facts) fill.
options:
  command:
    description:
      - The command to resolve (e.g. C(ls), C(date)).
    type: str
    required: true
extends_documentation_fragment:
  - o0_o.core.evidence
author:
  - oØ.o (@o0-o)
notes:
  - This module is implemented as an action plugin and supports raw fallback.
"""

EXAMPLES = r"""
- name: Find the path to date
  o0_o.posix.which:
    command: date
  register: date_path

- name: Show
  ansible.builtin.debug:
    var: date_path.path
"""

RETURN = r"""
path:
  description: Full path to the command if found
  type: str
  returned: always
  sample: /bin/date
o0_paths:
  description: >-
    The resolution as an observation of the file it resolved to.
    A built-in names no file and a lookup that missed names no path
    it was not at, so both leave the store unmentioned.
  returned: when the command resolved to a path
  type: dict
  contains:
    evidence:
      description: >-
        What the resolution consulted, in the collection's one
        provenance vocabulary. The lookup is a shell snippet rather
        than an argv - C(unalias -a) and then C(command -v) - so the
        shell that read it back is named beside the builtin it was
        asked, and C(id) is the probe that says whose answer the
        resolution is.
      type: dict
      sample:
        commands:
          - command
          - id
          - sh
    origins:
      description: >-
        The modules that composed the entry, by FQCN, sorted. It
        travels with C(evidence) and accumulates the same way, so a
        path this module and a gather both described names both of
        them. See the C(evidence) notes.
      type: list
      elements: str
      sample:
        - o0_o.posix.which
    executable:
      description: >-
        Whether the path can be run, keyed by the uid the lookup ran
        as. C(command -v) names a pathname the shell running it would
        run, which is that shell answering the question C(test -x)
        answers, and the answer belongs to whoever the shell was
        running as. A host that would not say who that was leaves the
        key off and the entry holds the path and nothing else.
      type: dict
      sample: {'0': true}
  sample:
    /bin/date:
      executable:
        '0': true
"""
from ansible.module_utils.basic import AnsibleModule


def main() -> None:
    """Fail if this module is run directly without the action plugin."""

    argument_spec = {"command": {"type": "str", "required": True}}

    module = AnsibleModule(
        argument_spec=argument_spec, supports_check_mode=True
    )
    module.fail_json(msg="This module must be run via its action plugin.")


if __name__ == "__main__":
    main()
