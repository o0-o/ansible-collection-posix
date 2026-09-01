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
name: schedule
short_description: Everything a host is configured to run on a schedule
version_added: "2.0.0"
description:
  - Join the crontab files in C(o0_paths) against the per-user
    crontabs in C(o0_users) and answer with one row per scheduled job,
    in one nomenclature, without running anything on the host.
  - There is no stored schedule fact and this is why. What a host runs
    on a schedule is two facts read together - the files a play could
    name, and the crontabs users hold - and a stored third copy of
    that join is a copy that can drift from the two it was copied out
    of. The join is derived at the moment it is asked instead.
  - Every row says where it came from. A row from a file names the
    C(path) it was read from; a row from a user's crontab names the
    C(uid) that holds it. Nothing else about a row depends on which of
    the two it was, which is the point of a normalized view.
  - The C(user) a job runs as comes from a different place in each
    case, and that difference is real rather than cosmetic. A system
    crontab and the files under C(/etc/cron.d) carry a user column,
    because they are root's statement about what runs as whom. A
    per-user crontab has none, because the spool it sits in answers
    that - so a row from one names the user only where C(o0_users)
    also carries a C(name) for that uid.
  - Where the host's kernel is known, a job its cron would refuse is
    left out, and a warning names it. This deliberately replicates
    what cron does at runtime with a line it cannot read - skip it and
    complain to syslog - because a schedule listing a job the host will
    never run describes a host that does not exist. The facts
    underneath still carry the job as written. The exclusion is the
    lookup's, not the fact's, and M(o0_o.posix.cron) warns about the
    same job at the moment it is read.
  - Whose spellings a host's cron takes is decided by the kernel and
    no further. POSIX spells a field as a number, a range, a comma list
    or C(*); the steps, the names, a weekday of C(7) and the eight
    special strings are Vixie's, which every supported cron takes;
    C(~) is OpenBSD's; C(@every_minute) and C(@every_second) are
    FreeBSD's. Linux is held to the union of what its crons take -
    cronie since 1.7 and Debian's cron both take OpenBSD's C(~),
    busybox takes neither that nor a weekday of C(7), and the kernel
    does not say which is running - so on Linux only FreeBSD's names
    are left out. The kernel is read from C(o0_os.kernel.name), with the
    setup module's C(ansible_system) as the fallback where no o0_o
    gather has run; a host naming neither gets every row and no
    verdict.
  - Only cron is joined here, and this lookup is the POSIX and
    Vixie-family baseline. An OS collection with a scheduler of its
    own - C(systemd) timers, C(launchd) - extends or replaces it with a
    schedule filter of its own, in this row shape, that knows the
    implementation the kernel does not name. Those filters live in the
    OS collections, and a play that reads schedules through them will
    not know the difference.
options:
  _terms:
    description:
      - Users to answer for, by UID or username.
      - Every scheduled job there is where no term is given.
      - A term that names no user answers nothing rather than
        failing, because a user with no scheduled work and a user the
        facts do not describe both run nothing.
    type: list
    elements: raw
  host:
    description:
      - Read C(o0_paths) and C(o0_users) from another host's variables
        rather than the current host's.
      - A host that has not gathered the facts answers nothing.
    type: str
notes:
  - This lookup reads the C(o0_paths) and C(o0_users) facts from the
    variable namespace and runs nothing on the host. Gather them
    first, with M(o0_o.posix.cron) or the C(cron) subset of
    M(o0_o.posix.facts); a namespace holding neither answers nothing.
  - Nothing here is a claim about when a job will next run. A schedule
    is kept as the crontab wrote it, and turning C(*/5) or C(@reboot)
    into a wall-clock time is a question about a host's clock,
    timezone and uptime rather than about its configuration.
  - The lookup does fail when C(o0_paths) or C(o0_users) is present
    but is not a dictionary, which is a namespace that cannot be read
    rather than one with nothing in it.
  - A row left out for a spelling the host's cron does not take is
    warned about once, naming the host, the crontab it came from by
    path or by uid, the field, the spelling, whose spelling it is, and
    the line - so the fix is one edit away. Only rows that would
    otherwise have been answered are held to the verdict, so asking
    about one user does not warn about another's crontab.
seealso:
  - module: o0_o.posix.cron
    description: Read the crontabs this lookup joins
  - plugin: o0_o.posix.homes
    plugin_type: lookup
    description: The same kind of derived view, over homes
"""

EXAMPLES = r"""
- name: Gather the facts the lookup reads
  o0_o.posix.cron:
    gather: true
  become: true

- name: Everything this host runs on a schedule
  ansible.builtin.debug:
    msg: "{{ lookup('o0_o.posix.schedule', wantlist=True) }}"

- name: What one user is scheduled to run
  ansible.builtin.debug:
    msg: "{{ lookup('o0_o.posix.schedule', 'alice', wantlist=True) }}"

- name: Fail where anything at all runs at boot
  ansible.builtin.assert:
    that:
      - >-
        lookup('o0_o.posix.schedule', wantlist=True)
        | selectattr('schedule.special', 'defined')
        | selectattr('schedule.special', 'eq', 'reboot')
        | list | length == 0
    fail_msg: Something on this host runs at boot

- name: Name every job root is configured to run
  ansible.builtin.debug:
    msg: >-
      {{ lookup('o0_o.posix.schedule', 0, wantlist=True)
         | map(attribute='command') | list }}

- name: Read another host's schedule
  ansible.builtin.debug:
    msg: >-
      {{ lookup('o0_o.posix.schedule', host='db1', wantlist=True) }}
"""

RETURN = r"""
_raw:
  description:
    - One row per scheduled job, the file-derived rows first and each
      source's rows in the order its crontab wrote them.
  type: list
  elements: dict
  contains:
    source:
      description:
        - Which of the two joined facts the row came from - C(file)
          for a crontab the host holds as a file, C(user) for one a
          user holds.
      returned: always
      type: str
      choices:
        - file
        - user
      sample: file
    path:
      description:
        - The C(o0_paths) key the row was read from.
        - Absent on a row from a user's crontab, which is filed under
          a uid rather than a path.
      returned: when source is file
      type: str
      sample: /etc/cron.d/zz-example
    uid:
      description:
        - The uid whose crontab the row was read from.
        - Absent on a row from a file.
      returned: when source is user
      type: int
      sample: 1000
    user:
      description:
        - The user the job runs as - the user column where the file
          has one, and the name C(o0_users) gives the uid otherwise.
        - Absent where nothing says. A per-user crontab names no user
          and a gather that did not read C(/etc/passwd) gives its uid
          no name, so the C(uid) is what identifies the row.
      returned: when anything names one
      type: str
      sample: root
    schedule:
      description:
        - When the job runs, as the crontab wrote it - the five fields
          C(minute), C(hour), C(day), C(month) and C(weekday), or
          C(special) naming one of cron's own such as C(reboot) or
          C(daily).
      returned: always
      type: dict
      sample:
        minute: '5'
        hour: '*'
        day: '*'
        month: '*'
        weekday: '*'
    command:
      description: What the job runs, as the crontab wrote it.
      returned: always
      type: str
      sample: /usr/bin/dropin-job --now
    environment:
      description:
        - What the crontab holding this job set for every job in it -
          C(SHELL), C(PATH), C(MAILTO) and whatever else it assigned.
        - Carried on the row rather than left to be looked up, because
          a job's command means something different under a different
          C(PATH), and a row that did not say would be describing half
          of what runs.
        - Empty where the crontab set nothing.
      returned: always
      type: dict
      sample:
        SHELL: /bin/sh
  sample:
    - source: file
      path: /etc/cron.d/zz-example
      user: root
      schedule:
        minute: '5'
        hour: '*'
        day: '*'
        month: '*'
        weekday: '*'
      command: /usr/bin/dropin-job --now
      environment:
        SHELL: /bin/sh
    - source: user
      uid: 1000
      user: alice
      schedule:
        special: reboot
      command: /usr/local/bin/alice-boot
      environment:
        MAILTO: alice@example.com
"""

from typing import Any, Optional

from ansible.errors import AnsibleLookupError
from ansible.plugins.lookup import LookupBase

from ansible_collections.o0_o.core.plugins.module_utils import (
    VarsLookupBase,
)
from ansible_collections.o0_o.posix.plugins.module_utils import (
    lookup_user,
)
from ansible_collections.o0_o.posix.plugins.module_utils.cron_utils import (
    cron_dialects,
    cron_kernel_name,
    describe_refusal,
    render_cron_job,
    schedule_refusal,
)

# Which of the two joined facts a row came from
FILE = "file"
USER = "user"

__all__ = ["LookupModule"]


class LookupModule(LookupBase, VarsLookupBase):
    """Everything a host is configured to run on a schedule."""

    def run(
        self,
        terms: list[Any],
        variables: Optional[dict[str, Any]] = None,
        **kwargs: Any,
    ) -> list[dict[str, Any]]:
        """Perform the lookup.

        :param list terms: Users to answer for, by UID or username;
            none for every scheduled job there is
        :param dict variables: Available Ansible variables
        :returns list: One row per scheduled job the host's cron would
            run
        :raises AnsibleLookupError: If a fact is not the shape it has
            to be
        """
        paths = self._mapping("o0_paths", **kwargs)
        users = self._mapping("o0_users", **kwargs)

        wanted = self._wanted(terms, users)

        rows = self._file_rows(paths)
        rows.extend(self._user_rows(users))

        if wanted is not None:
            rows = [row for row in rows if self._names(row, wanted)]

        return self._runnable(rows, **kwargs)

    def _kernel(self, **kwargs: Any) -> Optional[str]:
        """The kernel the host's variables name, or None.

        :returns Optional[str]: The kernel name folded the way o0_os
            folds it, from o0_os.kernel.name or ansible_system
        """
        return cron_kernel_name(
            {
                name: self.lookup_var(name, default=None, **kwargs)
                for name in ("o0_os", "ansible_facts", "ansible_system")
            }
        )

    def _runnable(
        self,
        rows: list[dict[str, Any]],
        **kwargs: Any,
    ) -> list[dict[str, Any]]:
        """The rows the host's cron would run.

        Where the kernel is known, a row its cron would refuse is left
        out and warned about, which is what cron does with the line at
        runtime: skip it, and complain to syslog.  Where the kernel is
        not known every row stands, because no verdict is better than
        a wrong one.

        :param list[dict[str, Any]] rows: The rows that would be
            answered
        :returns list[dict[str, Any]]: Those of them the host's cron
            takes
        """
        kernel = self._kernel(**kwargs)
        dialects = cron_dialects(kernel)
        if dialects is None:
            return rows

        host = self.lookup_var("inventory_hostname", default=None, **kwargs)
        prefix = f"[{host}] " if isinstance(host, str) and host else ""

        kept: list[dict[str, Any]] = []
        for row in rows:
            refusal = schedule_refusal(row.get("schedule"), dialects)
            if refusal is None:
                kept.append(row)
                continue

            source = (
                row["path"]
                if row.get("source") == FILE
                else f"uid {row.get('uid')}'s crontab"
            )
            self._display.warning(
                f"{prefix}{source}: {describe_refusal(refusal, kernel)},"
                f" so the job is left out of the schedule:"
                f" {render_cron_job(row)}"
            )

        return kept

    def _mapping(self, name: str, **kwargs: Any) -> dict[str, Any]:
        """Read one fact, holding it to being a mapping.

        :param str name: The fact to read
        :returns dict[str, Any]: What it holds, empty where it is not
            there
        :raises AnsibleLookupError: If it is there and is not a
            mapping
        """
        fact = self.lookup_var(name, default={}, **kwargs)

        if not isinstance(fact, dict):
            raise AnsibleLookupError(
                f"'{name}' fact is not a dictionary, got "
                f"{type(fact).__name__}"
            )

        return fact

    def _wanted(
        self,
        terms: list[Any],
        users: dict[str, Any],
    ) -> Optional[set[str]]:
        """The uids and names a term list asked about.

        :param list[Any] terms: The terms as they were asked
        :param dict[str, Any] users: The o0_users fact
        :returns Optional[set[str]]: What was asked about, or None
            where everything was
        """
        if not terms:
            return None

        wanted: set[str] = set()

        for term in terms:
            asked = self._templar.template(term)
            wanted.add(str(asked))

            entry = lookup_user(asked, users)
            if isinstance(entry, dict):
                for key in ("uid", "name"):
                    value = entry.get(key)
                    if value is not None:
                        wanted.add(str(value))

        return wanted

    @staticmethod
    def _names(row: dict[str, Any], wanted: set[str]) -> bool:
        """Whether one row is about somebody who was asked about.

        :param dict[str, Any] row: One scheduled job
        :param set[str] wanted: The uids and names asked about
        :returns bool: True where the row names one of them
        """
        return any(
            str(row[key]) in wanted for key in ("uid", "user") if key in row
        )

    @staticmethod
    def _jobs(config: Any) -> tuple[dict[str, str], list[dict[str, Any]]]:
        """What one crontab set and what it runs.

        :param Any config: A crontab's parsed configuration
        :returns tuple[dict[str, str], list[dict[str, Any]]]: The
            environment and the jobs, empty where it holds neither
        """
        if not isinstance(config, dict):
            return {}, []

        environment = config.get("environment")
        jobs = config.get("jobs")

        return (
            environment if isinstance(environment, dict) else {},
            jobs if isinstance(jobs, list) else [],
        )

    def _file_rows(self, paths: dict[str, Any]) -> list[dict[str, Any]]:
        """The rows the crontab files hold.

        :param dict[str, Any] paths: The o0_paths store
        :returns list[dict[str, Any]]: One row per job, by path
        """
        rows: list[dict[str, Any]] = []

        for path in sorted(paths):
            entry = paths[path]
            if not isinstance(entry, dict):
                continue

            environment, jobs = self._jobs(entry.get("config"))

            for job in jobs:
                if not isinstance(job, dict):
                    continue

                row = {
                    "source": FILE,
                    "path": path,
                    "schedule": job.get("schedule"),
                    "command": job.get("command"),
                    "environment": environment,
                }
                # A file that names who each job runs as is root
                # saying so; one that does not is not this lookup's to
                # guess at
                if job.get("user") is not None:
                    row["user"] = job["user"]

                rows.append(row)

        return rows

    def _user_rows(self, users: dict[str, Any]) -> list[dict[str, Any]]:
        """The rows the users' own crontabs hold.

        :param dict[str, Any] users: The o0_users fact
        :returns list[dict[str, Any]]: One row per job, by uid
        """
        rows: list[dict[str, Any]] = []

        for key in sorted(users, key=lambda uid: (len(uid), uid)):
            entry = users[key]
            if not isinstance(entry, dict):
                continue

            environment, jobs = self._jobs(entry.get("crontab"))

            for job in jobs:
                if not isinstance(job, dict):
                    continue

                row: dict[str, Any] = {
                    "source": USER,
                    "schedule": job.get("schedule"),
                    "command": job.get("command"),
                    "environment": environment,
                }

                uid = entry.get("uid")
                row["uid"] = uid if isinstance(uid, int) else int(key)

                # The spool answers whose crontab it is, so the row is
                # named only where a producer that read the passwd
                # file put a name on the uid
                name = entry.get("name")
                if isinstance(name, str) and name:
                    row["user"] = name

                rows.append(row)

        return rows
