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
module: shells
short_description: Run a host's login shells and report what they do
version_added: "2.0.0"
description:
  - Names the login shells the host claims, out of C(/etc/shells), and
    reports what running them produced.
  - A shell's configuration is code, so running it is the only honest
    way to know what it does. Two probes are run - the shell named by
    the C(shell) option out of C(/dev/null), which is what a login
    shell does before any user's dot files enter into it, and the
    login of each identity this run can reach, each out of its own
    home.
  - Answers the same shape M(o0_o.posix.facts) publishes as
    C(o0_shells), from the same planning and the same composer, so a
    gather and this module cannot disagree about what a shell turned
    out to do. Set C(gather) to publish it as a fact.
  - What a previous gather published is consulted rather than asked
    for again. A shell C(o0_paths) has confirmed absent is not run,
    and where this run cannot drop into a login, the connecting user's
    own pair is named from the C(o0_users) entry a previous gather or
    M(o0_o.posix.users) composed.
options:
  shell:
    description:
      - The shell to observe out of C(/dev/null), the canonical home
        no host has as a directory.
    type: str
    default: /bin/sh
  gather:
    description:
      - Publish the answer under C(ansible_facts) as well as
        returning it.
      - The namespaces are C(o0_shells) and C(o0_paths), the same
        names and the same shapes M(o0_o.posix.facts) publishes, so a
        later gather merges into them rather than replacing them.
    type: bool
    default: false
extends_documentation_fragment:
  - o0_o.core.evidence
author:
  - oØ.o (@o0-o)
notes:
  - This module is implemented as an action plugin and supports raw
    fallback.
  - >-
    A run that is root asks every probe through a login C(su), which
    resets the environment to what the user really gets. Run bare
    under C(become), a probe reports the environment C(sudo) left it
    and would file that as though it were the shell's. Only root can
    drop - C(su) asks everybody else for a password on a terminal a
    probe does not have - so a run that is not root observes the
    system layer and the one login it is already inside.
  - >-
    Nothing here runs every shell the host names. A probe is a shell
    run, and running each one on the chance somebody logs in with it
    is a cost with no answer attached, so a shell that was named and
    not run keeps its key with an empty mapping under it.
  - >-
    M(o0_o.posix.users) reads the same file and publishes the same
    keys with nothing under them, because it names shells and runs
    none.
"""

EXAMPLES = r"""
- name: Ask what this host's login shells do
  o0_o.posix.shells:
  register: host_shells

- name: Show the mask a login out of the system home would set
  ansible.builtin.debug:
    msg: >-
      {{ host_shells.shells['/bin/sh'].homes['/dev/null'].umask }}

- name: Observe a shell other than the default out of the system home
  o0_o.posix.shells:
    shell: /bin/ksh
  become: true

- name: Publish the answer as a fact instead of reading the return
  o0_o.posix.shells:
    gather: true
  become: true

- name: Fail where a login shell exports a modified IFS
  ansible.builtin.assert:
    that:
      - >-
        host_shells.shells | dict2items
        | selectattr('value.homes', 'defined')
        | map(attribute='value.homes') | map('dict2items') | flatten
        | map(attribute='value.env') | selectattr('IFS', 'defined')
        | list | length == 0
    fail_msg: A login shell exports IFS
"""

RETURN = r"""
shells:
  description:
    - The login shells the host names, keyed by shell path, and under
      each of them what running it out of a given home produced.
      C(user.shell in shells) reads as it does against the fact.
    - The pair decides the answer and neither half decides it alone -
      two users sharing a shell get whatever their own dot files make,
      and one user's two shells read two different sets of files - so
      the home is a key and not a field. Those keys live under
      C(homes), a mapping of its own, so a home path is never a key
      beside a field of the shell.
    - A key is the name the host uses, and the name is what decides
      behavior - C(bash) invoked as C(sh) is in POSIX mode and invoked
      as C(rbash) is restricted, so C(/bin/sh) and C(/usr/bin/bash)
      are two observations of one file and both are kept. What they
      share is C(binary).
    - A shell with an empty mapping under it was named and not run.
      Empty overall where the host names none and would run none.
    - The same shape C(o0_shells) has, described in full there.
  returned: always
  type: dict
  contains:
    homes:
      description:
        - What running this shell out of each home produced, keyed by
          home - the C(env) it had set, the C(umask) it would create
          files under, the C(locale) it reported and the C(aliases) it
          had defined. A field the shell would not answer is left out.
        - Every variable C(env) watches is answered on every probed
          row - its value where the shell exported one, C(null) where
          it did not - because C(env) prints the whole exported
          environment and so the answer is known either way.
      type: dict
    builtins:
      description: >-
        The commands the shell answers itself rather than by running a
        file, sorted. Enumerated by M(o0_o.posix.compliance) rather
        than here, so it is present on an entry a gather composed.
      type: list
      elements: str
    binary:
      description: >-
        The file this name finally resolves to - the last step of the
        chain C(o0_paths) walked, copied rather than walked again. A
        shell no read reached carries no pointer.
      type: str
      sample: /usr/bin/bash
    evidence:
      description: >-
        What was consulted about this shell, in the collection's one
        provenance vocabulary. One record per shell, the union of
        everything asked of it. A shell nothing was asked of carries
        none - the host's claim that it is a login shell is the
        C(/etc/shells) entry of C(o0_paths).
      type: dict
    origins:
      description: >-
        The modules that composed the entry, by FQCN, sorted. It
        travels with C(evidence) and accumulates the same way. See the
        C(evidence) notes.
      type: list
      elements: str
      sample:
        - o0_o.posix.shells
  sample:
    /bin/bash: {}
    /bin/sh:
      binary: /usr/bin/bash
      evidence:
        commands:
          - alias
          - env
          - locale
          - sh
          - su
          - umask
      homes:
        /dev/null:
          env:
            IFS: null
            LANG: en_US.UTF-8
            LC_CTYPE: null
            NLSPATH: null
            PATH: /usr/bin:/bin
            TERM: xterm
            TZ: null
          umask: '0022'
      origins:
        - o0_o.posix.shells
o0_paths:
  description:
    - The paths this module described, keyed by canonical absolute
      path, in the one flat store every producer of a path fact fills.
    - C(/etc/shells) is here because what a file names is a fact about
      that file - the bytes under C(content), the names they hold
      under C(config). A host with no C(/etc/shells) leaves the path
      out rather than filing a null there.
    - Each shell is here too, with what a read of that path says and
      every step it resolves through, because the question a consumer
      has about C(/bin/sh) is what it really is. The join with
      C(shells) is the path string.
    - Empty where the file would not be read and no shell was
      described.
  returned: always
  type: dict
  sample:
    /bin/sh:
      resolution:
        - /usr/bin/bash
      target: bash
      type: link
    /etc/shells:
      config:
        - /bin/sh
        - /bin/bash
      evidence:
        commands:
          - cat
ansible_facts:
  description: >-
    C(o0_shells) and C(o0_paths), the same names and shapes
    M(o0_o.posix.facts) publishes, so a later gather merges into them.
  returned: when gather is true and something was described
  type: dict
"""
from ansible.module_utils.basic import AnsibleModule


def main() -> None:
    """Fail if this module is run directly without the action plugin."""

    argument_spec = {
        "shell": {"type": "str", "default": "/bin/sh"},
        "gather": {"type": "bool", "default": False},
    }

    module = AnsibleModule(
        argument_spec=argument_spec, supports_check_mode=True
    )
    module.fail_json(msg="This module must be run via its action plugin.")


if __name__ == "__main__":
    main()
