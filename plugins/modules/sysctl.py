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
module: sysctl
short_description: Report and set the kernel's own tunables
version_added: "2.0.0"
description:
  - Reports what the kernel says its tunables are, and sets the ones a
    task names.
  - An inquiry rather than a fact. C(sysctl) is not a POSIX interface
    and its keys are not portable - what a key is called, what its
    values mean and which of them exist differ by kernel and by
    version - so nothing is published to C(ansible_facts) and nothing
    here claims to know what a value signifies.
  - Values come back verbatim, as the strings the host printed. A
    number is not converted, because a number here may be a count, a
    bitmask, a flag or a tuple of all three depending on which kernel
    answered, and typing it would be this collection guessing.
options:
  name:
    description:
      - The keys to report, each written as the host writes it.
      - Every key the host prints where none is named.
      - A key the host has no answer for is reported C(null) rather
        than left out, and rather than failing the task. The task named
        it, so the answer is about that key, and C(null) is this
        collection's word for asked about and not there.
    type: list
    elements: str
  values:
    description:
      - The keys to set, each with the value to set it to.
      - A mapping rather than a list of assignments, so one task cannot
        name a key twice with two values.
      - Idempotent. What the host says now is read first, compared as
        the string it is, and only a key whose value differs is set, so
        a task that asks for what is already in force reports no
        change.
      - A key the host refuses fails the task, naming it. A read-only
        key and an unprivileged session both refuse, and either way the
        value asked for is not the value in force, which must not read
        as success.
    type: dict
extends_documentation_fragment:
  - o0_o.core.evidence
author:
  - oØ.o (@o0-o)
notes:
  - This module is implemented as an action plugin and supports raw
    fallback.
  - >-
    Runtime values only, and that is the whole of this module's scope.
    Setting a tunable in the running kernel is the one interface every
    implementation shares, which is why it is the interface here.
  - >-
    Persistence is per-OS business and belongs to the OS collections,
    which extend this module rather than duplicate it - a
    C(sysctl.d) drop-in on Linux, C(sysctl.conf) on the BSDs, and
    nothing at all on macOS. An OS collection's own sysctl module adds
    a persistence option on top and delegates the runtime set here.
  - >-
    A POSIX host need not have C(sysctl) at all, and one that does not
    fails the task plainly, naming the absence. An explicit inquiry may
    fail loud where a gather would rather report nothing.
  - >-
    Setting a tunable usually requires privilege. Use C(become: true).
"""

EXAMPLES = r"""
- name: Ask the host for every tunable it prints
  o0_o.posix.sysctl:
  register: tunables

- name: Ask about the keys a play cares about
  o0_o.posix.sysctl:
    name:
      - kernel.hostname
      - vm.swappiness
      - net.ipv4.ip_forward
  register: some

- name: Tell a key the host does not have from one it does
  ansible.builtin.assert:
    that:
      - some.sysctl['vm.swappiness'] is not none
    fail_msg: This kernel has no vm.swappiness

- name: Set a tunable in the running kernel
  o0_o.posix.sysctl:
    values:
      net.ipv4.ip_forward: "1"
      vm.swappiness: "10"
  become: true

- name: Set one and report several
  o0_o.posix.sysctl:
    values:
      vm.swappiness: "10"
    name:
      - vm.swappiness
      - vm.dirty_ratio
  become: true

- name: See what a change would do without making it
  o0_o.posix.sysctl:
    values:
      kernel.sysrq: "0"
  become: true
  check_mode: true
  diff: true
  register: proposed

- name: Read a multiline value back the way the kernel holds it
  ansible.builtin.debug:
    msg: "{{ tunables.sysctl['kernel.core_modes'].splitlines() }}"
"""

RETURN = r"""
sysctl:
  description:
    - The tunables the task asked about, keyed by key, each holding the
      value the host printed for it as a verbatim string.
    - Every key the host prints where the task named none.
    - A key the host has no answer for is C(null). A key nobody asked
      about is not here at all, which is the other half of the same
      contract.
    - A multiline value comes back as one string carrying the newlines
      it was printed with. Two implementations spell it two ways and
      both mean the kernel holds a string with a newline in it - the
      BSDs print the rest of the value as indented lines of their own,
      and Linux prints the key again on every line - so either way it
      is joined back into the one value the kernel holds.
    - Where a value was set, this is what the kernel says afterwards
      rather than what it was asked to hold, because a value it
      normalized on the way in is its answer and the task's string was
      only a request.
  returned: always
  type: dict
  sample:
    kernel.core_modes: "file\npipe\nsocket"
    kernel.hostname: casa-hank
    kernel.nosuchkey: null
    vm.swappiness: '60'
evidence:
  description:
    - What the answer consulted, in the collection's one provenance
      vocabulary.
    - One command answers every question here, whether it was asked to
      read or to write.
  returned: always
  type: dict
  sample:
    commands:
      - sysctl
"""
from ansible.module_utils.basic import AnsibleModule


def main() -> None:
    """Fail if this module is run directly without the action plugin."""

    argument_spec = {
        "name": {"type": "list", "elements": "str"},
        "values": {"type": "dict"},
    }

    module = AnsibleModule(
        argument_spec=argument_spec, supports_check_mode=True
    )
    module.fail_json(msg="This module must be run via its action plugin.")


if __name__ == "__main__":
    main()
