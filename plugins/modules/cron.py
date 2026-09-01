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
module: cron
short_description: Report what a host is configured to run on a schedule
version_added: "2.0.0"
description:
  - Reads the crontabs a host holds and reports what each one
    schedules.
  - Two facts, because a crontab is two different things depending on
    where it sits. C(/etc/crontab) and the files under C(/etc/cron.d)
    are files a play could name, so what they schedule is a fact about
    them and lands in C(o0_paths) beside their bytes, the way
    C(/etc/fstab) carries the filesystems it names. A per-user crontab
    is a fact about the user who owns it and lands under their UID in
    C(o0_users).
  - There is no schedule namespace of its own. What a host runs on a
    schedule is those two answers joined, and the
    P(o0_o.posix.schedule#lookup) lookup is what joins them - a
    derived view rather than a third copy that could disagree with the
    two it came from.
  - C(anacron) is not read. Its table is a period, a delay, a job
    identifier and a command, with no user column and no schedule in
    cron's sense, so it shares a neighbourhood with cron and not a
    format.
options:
  gather:
    description:
      - Publish the answer under C(ansible_facts) as well as
        returning it.
      - The namespaces are C(o0_paths) and C(o0_users), the same names
        and shapes M(o0_o.posix.facts) publishes, so a later gather
        merges into them rather than replacing them.
    type: bool
    default: false
extends_documentation_fragment:
  - o0_o.posix.evidence
author:
  - oØ.o (@o0-o)
notes:
  - This module is implemented as an action plugin and supports raw
    fallback.
  - >-
    Whose crontabs can be read depends on who is asking. Any identity
    can read its own with C(crontab -l), which is the reading POSIX
    defines. Reading somebody else's means reading the spool, which is
    root's to read, so a run that is not root reports itself and says
    nothing about anyone else - rather than reporting that nobody else
    has one. Use C(become: true) to enumerate.
  - >-
    The spools are swept for names rather than the passwd file being
    read for them, so this costs one command whatever the host's user
    count and needs no other subset to have run first. C(crontab -u)
    is not used: it is a Vixie extension rather than POSIX, and a
    spool file is the crontab itself.
  - >-
    A user asked about who holds no crontab carries C(null), which is
    this collection's word for asked about and not there. A user
    nobody asked about is absent.
"""

EXAMPLES = r"""
- name: Ask what this host schedules
  o0_o.posix.cron:
  become: true
  register: scheduled

- name: Show what the system crontab runs
  ansible.builtin.debug:
    msg: >-
      {{ scheduled.o0_paths['/etc/crontab'].config.jobs }}

- name: Show whose crontabs were read
  ansible.builtin.debug:
    msg: >-
      {{ scheduled.o0_users | dict2items
         | rejectattr('value.crontab', 'none')
         | map(attribute='key') | list }}

- name: Publish the answer as facts instead of reading the return
  o0_o.posix.cron:
    gather: true
  become: true

- name: Fail where anything runs at boot without being reviewed
  ansible.builtin.assert:
    that:
      - >-
        scheduled.o0_users | dict2items
        | rejectattr('value.crontab', 'none')
        | map(attribute='value.crontab.jobs') | flatten
        | selectattr('schedule.special', 'defined')
        | selectattr('schedule.special', 'eq', 'reboot')
        | list | length == 0
    fail_msg: A user crontab runs a job at boot
"""

RETURN = r"""
o0_paths:
  description:
    - The crontab files this read described, keyed by canonical
      absolute path, in the one flat store every producer of a path
      fact fills.
    - C(/etc/crontab) and each file under C(/etc/cron.d) carry their
      bytes under C(content) and what they schedule under C(config).
      Only files whose rows carry a user column are here - a spool file
      is a crontab too and is read, but what it says is a fact about
      the user who owns it rather than about a path a play would name.
    - A file that would not be read is left out rather than filed as a
      null, because a C(cat) that failed cannot tell a file that is
      not there from one it could not read. Empty where the host holds
      no system crontab and no drop-ins.
  returned: always
  type: dict
  contains:
    content:
      description: The file's bytes, as they were read.
      type: str
    config:
      description:
        - What the file schedules - the C(environment) it sets for
          every job below, and the C(jobs) themselves in the order the
          file wrote them.
        - A job carries its C(schedule), the C(user) it runs as, and
          the C(command). A schedule is the five fields C(minute),
          C(hour), C(day), C(month) and C(weekday) as the file wrote
          them, or C(special) naming one of cron's own - C(reboot),
          C(daily) and their siblings.
      type: dict
  sample:
    /etc/cron.d/zz-example:
      content: "SHELL=/bin/sh\n5 * * * * root /usr/bin/dropin-job\n"
      config:
        environment:
          SHELL: /bin/sh
        jobs:
          - schedule:
              minute: '5'
              hour: '*'
              day: '*'
              month: '*'
              weekday: '*'
            user: root
            command: /usr/bin/dropin-job
      evidence:
        commands:
          - cat
o0_users:
  description:
    - The crontab each user holds, keyed by stringified UID, in the
      same namespace M(o0_o.posix.users) and M(o0_o.posix.facts)
      publish users under.
    - C(crontab) is what that user's crontab schedules, in the same
      shape a file's C(config) takes minus the user column - the spool
      the crontab sits in already answers whose it is.
    - A user asked about who holds no crontab carries C(null). A user
      nobody asked about is absent, which is every user but the
      running identity on a run that is not root.
  returned: always
  type: dict
  contains:
    uid:
      description: Numeric user ID, the integer the key stringifies.
      type: int
    crontab:
      description: What that user's crontab schedules, or null.
      type: dict
    evidence:
      description:
        - What was consulted, in the collection's one provenance
          vocabulary. The running identity's own crontab is read by
          C(crontab), the command POSIX defines for it; everybody
          else's is the spool file, named under C(files) and read the
          way every file here is read.
      type: dict
  sample:
    '1000':
      uid: 1000
      crontab:
        environment:
          MAILTO: alice@example.com
        jobs:
          - schedule:
              special: reboot
            command: /usr/local/bin/alice-boot
      evidence:
        files:
          - /var/spool/cron/alice
        commands:
          - cat
      origins:
        - o0_o.posix.cron
ansible_facts:
  description: >-
    C(o0_paths) and C(o0_users), the same names and shapes
    M(o0_o.posix.facts) publishes, so a later gather merges into them.
  returned: when gather is true and something was described
  type: dict
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
