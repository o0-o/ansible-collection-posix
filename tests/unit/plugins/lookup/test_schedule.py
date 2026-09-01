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

"""Unit tests for the schedule lookup plugin."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from ansible.errors import AnsibleLookupError

from ansible_collections.o0_o.posix.plugins.lookup.schedule import (
    LookupModule,
)

# What a host that schedules things looks like once both facts are in
PATHS = {
    "/etc/crontab": {
        "config": {
            "environment": {"SHELL": "/bin/sh", "PATH": "/usr/bin:/bin"},
            "jobs": [
                {
                    "schedule": {
                        "minute": "17",
                        "hour": "*",
                        "day": "*",
                        "month": "*",
                        "weekday": "*",
                    },
                    "user": "root",
                    "command": "run-parts /etc/cron.hourly",
                }
            ],
        }
    },
    "/etc/cron.d/zz-example": {
        "config": {
            "environment": {"SHELL": "/bin/sh"},
            "jobs": [
                {
                    "schedule": {
                        "minute": "5",
                        "hour": "*",
                        "day": "*",
                        "month": "*",
                        "weekday": "*",
                    },
                    "user": "postgres",
                    "command": "/usr/bin/dropin-job --now",
                }
            ],
        }
    },
}

USERS = {
    # A user asked about who holds no crontab
    "0": {"uid": 0, "name": "root", "crontab": None},
    "1000": {
        "uid": 1000,
        "name": "alice",
        "crontab": {
            "environment": {"MAILTO": "alice@example.com"},
            "jobs": [
                {
                    "schedule": {"special": "reboot"},
                    "command": "/usr/local/bin/alice-boot",
                },
                {
                    "schedule": {
                        "minute": "*/10",
                        "hour": "*",
                        "day": "*",
                        "month": "*",
                        "weekday": "*",
                    },
                    "command": "/usr/bin/alice-ten",
                },
            ],
        },
    },
    # A uid no passwd read put a name on, which is what a gather of
    # cron alone answers with
    "1001": {
        "uid": 1001,
        "crontab": {
            "environment": {},
            "jobs": [
                {
                    "schedule": {
                        "minute": "0",
                        "hour": "3",
                        "day": "*",
                        "month": "*",
                        "weekday": "mon-fri",
                    },
                    "command": "/usr/bin/bob-weekday",
                }
            ],
        },
    },
}


class FakeTemplar:
    """Stand in for the templar a lookup reads variables through."""

    def __init__(self, variables: dict[str, Any]) -> None:
        self.available_variables = variables

    def template(self, value: Any) -> Any:
        """Resolve a term the way the templar would."""
        return value


@pytest.fixture
def make_lookup():
    """Build a lookup reading a namespace the test supplies.

    :returns: A factory taking the namespace as keyword arguments
    """

    def _make(**variables: Any) -> LookupModule:
        lookup = LookupModule(
            loader=None, templar=FakeTemplar(variables)
        )
        lookup._display = MagicMock()
        return lookup

    return _make


@pytest.fixture
def scheduled(make_lookup):
    """A lookup over a host that schedules things both ways."""
    return make_lookup(o0_paths=PATHS, o0_users=USERS)


def _commands(rows: list[dict[str, Any]]) -> list[str]:
    """The commands a set of rows names, in order."""
    return [row["command"] for row in rows]


def test_both_facts_are_joined_into_one_nomenclature(scheduled) -> None:
    """Test a row reads the same whichever fact it came from.

    Nothing about a row but where it came from depends on which of the
    two it was, which is the point of a normalized view.
    """
    rows = scheduled.run([], None)

    # Two files hold one job each, and two users hold three between
    # them; the user holding a null crontab holds no rows
    assert len(rows) == 5
    assert {row["source"] for row in rows} == {"file", "user"}
    assert all(
        set(row) >= {"source", "schedule", "command", "environment"}
        for row in rows
    )


def test_a_row_says_where_it_was_read_from(scheduled) -> None:
    """Test a file row names its path and a user row names its uid.

    Neither carries the other's key, because a crontab filed under a
    uid has no path and one read from a path has no uid.
    """
    rows = scheduled.run([], None)
    files = [row for row in rows if row["source"] == "file"]
    users = [row for row in rows if row["source"] == "user"]

    assert all("path" in row and "uid" not in row for row in files)
    assert all("uid" in row and "path" not in row for row in users)
    assert files[0]["path"] == "/etc/cron.d/zz-example"
    assert users[0]["uid"] == 1000


def test_the_user_column_is_who_a_file_row_runs_as(scheduled) -> None:
    """Test root's statement about what runs as whom is carried."""
    rows = scheduled.run([], None)
    dropin = next(
        row for row in rows if row.get("path", "").endswith("zz-example")
    )

    assert dropin["user"] == "postgres"


def test_a_user_row_is_named_only_where_something_names_it(
    scheduled,
) -> None:
    """Test the uid identifies a row that nothing put a name on.

    A per-user crontab names no user, because the spool it sits in
    answers that, so a gather that did not read the passwd file leaves
    the uid to identify the row.
    """
    rows = scheduled.run([], None)
    named = next(row for row in rows if row.get("uid") == 1000)
    unnamed = next(row for row in rows if row.get("uid") == 1001)

    assert named["user"] == "alice"
    assert "user" not in unnamed


def test_the_environment_a_job_runs_under_rides_with_it(
    scheduled,
) -> None:
    """Test a row says what its crontab set for it.

    A command means something different under a different PATH, so a
    row that did not say would describe half of what runs.
    """
    rows = scheduled.run([], None)
    system = next(row for row in rows if row.get("path") == "/etc/crontab")
    alice = next(row for row in rows if row.get("uid") == 1000)

    assert system["environment"] == {
        "SHELL": "/bin/sh",
        "PATH": "/usr/bin:/bin",
    }
    assert alice["environment"] == {"MAILTO": "alice@example.com"}


def test_a_schedule_is_carried_as_the_crontab_wrote_it(
    scheduled,
) -> None:
    """Test neither form of schedule is converted into the other."""
    rows = scheduled.run([], None)
    special = next(
        row for row in rows if row["schedule"].get("special") is not None
    )
    fielded = next(
        row for row in rows if row["schedule"].get("minute") == "*/10"
    )

    assert special["schedule"] == {"special": "reboot"}
    assert fielded["schedule"]["weekday"] == "*"


@pytest.mark.parametrize("term", ["alice", 1000, "1000"])
def test_a_term_selects_a_user_by_name_or_uid(scheduled, term) -> None:
    """Test the rows come back for whoever was asked about."""
    rows = scheduled.run([term], None)

    assert _commands(rows) == [
        "/usr/local/bin/alice-boot",
        "/usr/bin/alice-ten",
    ]


def test_a_term_selects_an_unnamed_uid(scheduled) -> None:
    """Test a uid nothing named is still selectable by its uid."""
    rows = scheduled.run([1001], None)

    assert _commands(rows) == ["/usr/bin/bob-weekday"]


def test_a_term_selects_a_file_row_by_its_user_column(
    scheduled,
) -> None:
    """Test asking about a user finds what a file schedules for them.

    A user's scheduled work is not only what is in their own crontab:
    root's files run jobs as other people.
    """
    rows = scheduled.run(["postgres"], None)

    assert _commands(rows) == ["/usr/bin/dropin-job --now"]


def test_a_user_who_schedules_nothing_answers_nothing(
    scheduled,
) -> None:
    """Test a user with a null crontab contributes no rows.

    root holds no crontab here and still runs the system crontab's
    jobs, which are the file's rows and named as such.
    """
    rows = scheduled.run(["root"], None)

    assert _commands(rows) == ["run-parts /etc/cron.hourly"]


def test_a_term_naming_nobody_answers_nothing(scheduled) -> None:
    """Test an unknown user runs nothing rather than failing.

    A user with no scheduled work and a user the facts do not describe
    both run nothing.
    """
    assert scheduled.run(["nosuchuser"], None) == []


def test_a_host_that_gathered_nothing_schedules_nothing(
    make_lookup,
) -> None:
    """Test an empty namespace answers with no rows."""
    assert make_lookup().run([], None) == []


def test_a_host_with_only_one_of_the_two_facts_answers_it(
    make_lookup,
) -> None:
    """Test the join does not need both halves to be there."""
    files_only = make_lookup(o0_paths=PATHS)
    users_only = make_lookup(o0_users=USERS)

    assert len(files_only.run([], None)) == 2
    assert len(users_only.run([], None)) == 3


@pytest.mark.parametrize("fact", ["o0_paths", "o0_users"])
def test_a_fact_that_is_not_a_mapping_fails(make_lookup, fact) -> None:
    """Test a namespace that cannot be read is not read as empty."""
    lookup = make_lookup(**{fact: "not a mapping"})

    with pytest.raises(AnsibleLookupError, match="not a dictionary"):
        lookup.run([], None)


def test_an_entry_that_is_not_a_mapping_is_passed_over(
    make_lookup,
) -> None:
    """Test one malformed entry does not take the answer with it.

    A store holding a null at a path is the absence contract working,
    and a path that answered nothing schedules nothing.
    """
    lookup = make_lookup(
        o0_paths={**PATHS, "/etc/cron.d/unread": None},
        o0_users={**USERS, "2": None},
    )

    assert len(lookup.run([], None)) == 5


def test_nothing_here_claims_when_a_job_will_next_run(
    scheduled,
) -> None:
    """Test the rows carry configuration and never a wall-clock time.

    Turning */5 or @reboot into a time is a question about a host's
    clock, timezone and uptime rather than about its configuration.
    """
    rows = scheduled.run([], None)

    assert all(
        set(row["schedule"])
        <= {"minute", "hour", "day", "month", "weekday", "special"}
        for row in rows
    )
    assert all("next" not in row for row in rows)


# --- What the host's cron would refuse is left out -----------------------

# A drop-in spelled the OpenBSD way, and a user who names a FreeBSD
# schedule, on hosts whose crons take one, the other, or neither
RANDOM_DROPIN = {
    "/etc/cron.d/random": {
        "config": {
            "environment": {},
            "jobs": [
                {
                    "schedule": {
                        "minute": "~",
                        "hour": "2",
                        "day": "*",
                        "month": "*",
                        "weekday": "6",
                    },
                    "user": "root",
                    "command": "/bin/sh /etc/weekly",
                }
            ],
        }
    }
}
TICKER = {
    "1002": {
        "uid": 1002,
        "name": "carol",
        "crontab": {
            "environment": {},
            "jobs": [
                {
                    "schedule": {"special": "every_second"},
                    "command": "/usr/local/bin/tick",
                }
            ],
        },
    }
}


def _warnings(lookup: LookupModule) -> list[str]:
    """Every warning the lookup displayed, as text."""
    return [
        str(call.args[0]) for call in lookup._display.warning.call_args_list
    ]


def test_a_job_the_hosts_cron_would_refuse_is_left_out(make_lookup) -> None:
    """Test a row cron would skip at runtime is skipped here too.

    Neither a ~ nor an @every_second is anything Darwin's cron reads,
    so a schedule that listed them would describe a host that does not
    exist. The warning replaces the syslog complaint.
    """
    lookup = make_lookup(
        o0_paths={**PATHS, **RANDOM_DROPIN},
        o0_users={**USERS, **TICKER},
        o0_os={"kernel": {"name": "darwin"}},
        inventory_hostname="db1",
    )

    rows = lookup.run([], None)
    warned = _warnings(lookup)

    assert len(rows) == 5
    assert "/bin/sh /etc/weekly" not in _commands(rows)
    assert "/usr/local/bin/tick" not in _commands(rows)
    assert len(warned) == 2
    assert warned[0].startswith("[db1] /etc/cron.d/random: minute '~' is an")
    assert "left out of the schedule" in warned[0]
    assert warned[0].endswith("~ 2 * * 6 root /bin/sh /etc/weekly")
    assert warned[1].startswith("[db1] uid 1002's crontab: '@every_second'")


def test_linux_keeps_the_tilde_and_not_freebsds_names(make_lookup) -> None:
    """Test Linux is held to what every Linux cron takes.

    cronie and Debian's cron take the tilde and busybox does not, and
    the kernel does not say which is running, so the tilde row stands
    and only FreeBSD's name goes.
    """
    lookup = make_lookup(
        o0_paths={**PATHS, **RANDOM_DROPIN},
        o0_users={**USERS, **TICKER},
        o0_os={"kernel": {"name": "linux"}},
    )

    rows = lookup.run([], None)

    assert "/bin/sh /etc/weekly" in _commands(rows)
    assert "/usr/local/bin/tick" not in _commands(rows)
    assert len(_warnings(lookup)) == 1


def test_without_a_kernel_every_row_stands(make_lookup) -> None:
    """Test no kernel means no verdict, and no warning either."""
    lookup = make_lookup(
        o0_paths={**PATHS, **RANDOM_DROPIN}, o0_users={**USERS, **TICKER}
    )

    rows = lookup.run([], None)

    assert len(rows) == 7
    assert _warnings(lookup) == []


def test_ansible_system_names_the_kernel_where_no_gather_ran(
    make_lookup,
) -> None:
    """Test the setup module's word for the kernel is read as a fallback.

    OpenBSD takes its own ~ and not FreeBSD's names, so one row stays
    and the other goes.
    """
    lookup = make_lookup(
        o0_paths={**PATHS, **RANDOM_DROPIN},
        o0_users={**USERS, **TICKER},
        ansible_system="OpenBSD",
    )

    rows = lookup.run([], None)

    assert "/bin/sh /etc/weekly" in _commands(rows)
    assert "/usr/local/bin/tick" not in _commands(rows)
    assert len(_warnings(lookup)) == 1


def test_o0_os_is_read_under_ansible_facts_too(make_lookup) -> None:
    """Test a gather that was not injected as variables still counts."""
    lookup = make_lookup(
        o0_paths={**PATHS, **RANDOM_DROPIN},
        ansible_facts={"o0_os": {"kernel": {"name": "freebsd"}}},
    )

    rows = lookup.run([], None)

    assert "/bin/sh /etc/weekly" not in _commands(rows)
    assert len(rows) == 2


def test_a_kernel_this_does_not_know_gets_no_verdict(make_lookup) -> None:
    """Test an unknown kernel leaves every row standing."""
    lookup = make_lookup(
        o0_paths={**PATHS, **RANDOM_DROPIN},
        o0_os={"kernel": {"name": "sunos"}},
    )

    assert len(lookup.run([], None)) == 3
    assert _warnings(lookup) == []


def test_only_rows_that_would_be_answered_are_held_to_the_verdict(
    make_lookup,
) -> None:
    """Test asking about one user does not warn about another's crontab."""
    lookup = make_lookup(
        o0_paths={**PATHS, **RANDOM_DROPIN},
        o0_users={**USERS, **TICKER},
        o0_os={"kernel": {"name": "linux"}},
    )

    rows = lookup.run(["alice"], None)

    assert _commands(rows) == [
        "/usr/local/bin/alice-boot",
        "/usr/bin/alice-ten",
    ]
    assert _warnings(lookup) == []

    assert lookup.run(["carol"], None) == []
    assert len(_warnings(lookup)) == 1


def test_the_verdict_follows_the_host_asked_about(make_lookup) -> None:
    """Test another host's rows are held to that host's kernel."""
    lookup = make_lookup(
        hostvars={
            "bsd1": {
                "o0_paths": RANDOM_DROPIN,
                "o0_users": TICKER,
                "o0_os": {"kernel": {"name": "freebsd"}},
                "inventory_hostname": "bsd1",
            }
        }
    )

    rows = lookup.run([], None, host="bsd1")

    assert _commands(rows) == ["/usr/local/bin/tick"]
    assert _warnings(lookup)[0].startswith("[bsd1] /etc/cron.d/random:")
