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
module: limits
short_description: Report the resource limits of the current session
version_added: "2.0.0"
description:
  - Asks the session this task runs in what it is limited to, and
    answers with the soft ceiling in force and the hard ceiling it may
    be raised to for each resource.
  - Deliberately not a fact. A resource limit belongs to one session
    rather than to a host or to a user, and it does not outlive the
    task that asked, so it comes back as a result and the play reads
    it where it asked. Nothing is published to C(ansible_facts).
  - Whose session gets asked is the play's to choose. Run the task as
    the identity whose limits are the question - C(become) and
    C(become_user) select it - and ask twice to have two answers.
options: {}
extends_documentation_fragment:
  - o0_o.posix.evidence
author:
  - oØ.o (@o0-o)
notes:
  - This module is implemented as an action plugin and supports raw
    fallback.
  - >-
    The answer describes the session Ansible reached, not the limits
    the target's configuration would grant a login. PAM applies
    C(limits.conf) once per service, so a connection that arrived over
    C(sshd) and then became root through C(sudo) or C(su) carries
    sshd's ceilings with whatever the later service overlaid on them -
    a service that names a resource replaces that resource's ceiling
    and the rest are inherited, and no step in the chain resets what
    an earlier one set.
  - >-
    A hard ceiling only ever falls in an unprivileged session, so a
    lowered hard limit anywhere in that chain is the floor for every
    limit reported beneath it, no matter what the configuration says.
    To read what a real login would get, ask over a connection that
    is one - not through a become chain.
  - >-
    C(become) itself is part of what is being measured. The same host
    answers differently with and without it, and both answers are
    correct about the session that gave them.
"""

EXAMPLES = r"""
- name: Ask what this session is limited to
  o0_o.posix.limits:
  register: session_limits

- name: Show the descriptor ceiling in force
  ansible.builtin.debug:
    msg: >-
      {{ session_limits.limits.open_files.soft }} of
      {{ session_limits.limits.open_files.hard }} descriptors

- name: Ask what a privileged session is limited to instead
  o0_o.posix.limits:
  become: true
  register: root_limits

- name: Fail where the connection cannot open enough files
  ansible.builtin.assert:
    that:
      - session_limits.limits.open_files.soft >= 4096
    fail_msg: >-
      This session may open
      {{ session_limits.limits.open_files.soft }} files
"""

RETURN = r"""
limits:
  description:
    - The session's resource limits, keyed by resource name.
    - Each resource carries the soft ceiling in force and the hard
      ceiling it may be raised to. An unlimited ceiling is null, and
      so is a ceiling the shell named in one set and not the other -
      a shell that answered the soft set and not the hard has not
      said the hard one is unlimited.
    - A resource reported in units carries the unit the shell printed
      it in. A resource counted in things does not.
    - Empty where the session's shell would not say. An empty mapping
      is a session that was asked, not a session without limits.
  returned: always
  type: dict
  sample:
    core:
      soft: 0
      hard: null
      unit: blocks
    open_files:
      soft: 1024
      hard: 524288
    processes:
      soft: 62883
      hard: 62883
uid:
  description:
    - The effective uid the answer came from, as reported by C(id -u).
    - A limit is only meaningful beside the identity it applies to,
      and a become chain means the identity in the play is not always
      the identity that answered.
    - Null where the host would not say who it ran as.
  returned: always
  type: int
  sample: 0
evidence:
  description:
    - What the answer consulted, in the collection's one provenance
      vocabulary.
    - C(ulimit) is a shell builtin rather than a program, and it is
      still the command that answered - the probe is a script, so the
      shell that read it back is not the subject. C(id) is what says
      whose session answered.
  returned: always
  type: dict
  sample:
    commands:
      - id
      - ulimit
"""
from ansible.module_utils.basic import AnsibleModule


def main() -> None:
    """Fail if this module is run directly without the action plugin."""

    module = AnsibleModule(argument_spec={}, supports_check_mode=True)
    module.fail_json(msg="This module must be run via its action plugin.")


if __name__ == "__main__":
    main()
