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

"""Unit tests for cron_utils module.

Four of the five corpora are live captures off running Linux, taken
from containers because the host this suite usually proves against has
no cron installed at all:

``crontab_etc_debian.txt`` is the ``/etc/crontab`` that
``docker.io/library/debian:stable`` ships once the ``cron`` package is
installed. ``crontab_etc_fedora.txt`` and ``crontab_cron_d_fedora.txt``
are ``registry.fedoraproject.org/fedora:latest``'s, with ``cronie``.
``crontab_user_cronie.txt`` is a per-user crontab installed into that
same image's real cronie spool and read back with ``crontab -l``.

``crontab_user_bsd.txt`` is written by hand in the form Vixie cron
writes on the BSDs and macOS, including the three header lines it
prepends and strips again, because no host of that family was in reach
to capture one from.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ansible_collections.o0_o.posix.plugins.module_utils.cron_utils import (
    parse_crontab,
)

FILES = Path(__file__).parent / "files"

# Which corpora came off a running host and which were written from the
# documented form
LIVE = ("etc_debian", "etc_fedora", "cron_d_fedora", "user_cronie")
CONSTRUCTED = ("user_bsd",)

# The files whose rows name the user to run as. A system crontab and
# the files under /etc/cron.d are root's statement about what runs as
# whom; a per-user crontab sits in a spool that answers that already.
USER_COLUMN = {
    "etc_debian": True,
    "etc_fedora": True,
    "cron_d_fedora": True,
    "user_cronie": False,
    "user_bsd": False,
}


def corpus(name: str) -> str:
    """Read one crontab corpus.

    :param str name: The corpus suffix
    :returns str: The file's contents
    """
    return (FILES / f"crontab_{name}.txt").read_text()


def parsed(name: str) -> dict:
    """Parse one crontab corpus the way its file would be read.

    :param str name: The corpus suffix
    :returns dict: What the crontab configures
    """
    return parse_crontab(corpus(name), user_column=USER_COLUMN[name])


@pytest.mark.parametrize("name", LIVE + CONSTRUCTED)
def test_a_crontab_is_two_kinds_of_line(name: str) -> None:
    """Test every corpus reaches the same two-part shape.

    Some lines set a variable for every job below them and some are
    jobs. Both are configuration and neither is the other.
    """
    config = parsed(name)

    assert set(config) == {"environment", "jobs"}
    assert all(
        isinstance(value, str)
        for value in config["environment"].values()
    )
    assert all(
        "schedule" in job and "command" in job for job in config["jobs"]
    )


def test_a_system_crontab_names_who_each_job_runs_as() -> None:
    """Test the user column is read where the file has one."""
    jobs = parsed("etc_debian")["jobs"]

    assert len(jobs) == 4
    assert all(job["user"] == "root" for job in jobs)
    assert jobs[0]["schedule"] == {
        "minute": "17",
        "hour": "*",
        "day": "*",
        "month": "*",
        "weekday": "*",
    }


def test_a_command_keeps_the_shell_text_it_is() -> None:
    """Test a command is the rest of the line, whatever is in it.

    Debian's own crontab runs commands carrying ``&&``, ``||`` and a
    braced list with a semicolon in it, and none of that is a field
    separator once the schedule and the user have been read.
    """
    jobs = parsed("etc_debian")["jobs"]

    assert jobs[1]["command"] == (
        "test -x /usr/sbin/anacron || "
        "{ cd / && run-parts --report /etc/cron.daily; }"
    )
    assert parsed("user_bsd")["jobs"][2]["command"] == (
        "/usr/local/bin/heartbeat >/dev/null 2>&1"
    )


def test_a_per_user_crontab_names_no_user() -> None:
    """Test the spool answers whose crontab it is, so the row need not.

    A row here that named a user would be reporting the first word of
    the command as one.
    """
    jobs = parsed("user_cronie")["jobs"]

    assert all("user" not in job for job in jobs)
    assert jobs[2]["command"] == "/usr/bin/every-five"


def test_the_special_strings_are_a_form_and_not_a_fallback() -> None:
    """Test cron's named schedules are understood as themselves."""
    jobs = parsed("user_cronie")["jobs"]

    assert jobs[0]["schedule"] == {"special": "reboot"}
    assert jobs[0]["command"] == "/usr/local/bin/boot-job --flag"
    assert jobs[1]["schedule"] == {"special": "daily"}
    assert parsed("user_bsd")["jobs"][1]["schedule"] == {"special": "weekly"}


def test_a_schedule_is_kept_as_the_file_wrote_it() -> None:
    """Test every spelling cron takes survives as itself.

    A step, a range, a list and a name are all cron's own way of
    writing a schedule and none is more canonical than another, so
    what is published is what a reader would find in the file.
    """
    schedules = [job["schedule"] for job in parsed("user_cronie")["jobs"]]

    assert schedules[2]["minute"] == "*/5"
    assert schedules[3]["weekday"] == "1-5"
    assert schedules[4]["day"] == "1,15"
    assert schedules[5]["month"] == "jan,feb"
    assert schedules[5]["weekday"] == "mon"


def test_the_environment_a_crontab_sets_is_read_apart() -> None:
    """Test an assignment is not a job and does not become one."""
    config = parsed("cron_d_fedora")

    assert config["environment"] == {
        "SHELL": "/bin/bash",
        "PATH": "/sbin:/bin:/usr/sbin:/usr/bin",
        "MAILTO": "root",
    }
    assert len(config["jobs"]) == 1


def test_a_crontab_that_sets_and_runs_nothing_says_so() -> None:
    """Test a file of assignments and comments holds no jobs.

    Fedora's own /etc/crontab is exactly that, and an empty job list is
    the truthful reading of it.
    """
    config = parsed("etc_fedora")

    assert config["jobs"] == []
    assert config["environment"]["MAILTO"] == "root"


def test_a_quoted_value_is_the_value_inside_the_quotes() -> None:
    """Test the quotes are syntax, the way cron reads them.

    A value is quoted to keep whitespace cron would trim, so what a
    job sees is what is inside them.
    """
    environment = parsed("user_bsd")["environment"]

    assert environment["MAILTO"] == ""
    assert environment["HOME"] == "/home/operator"
    assert parse_crontab('FOO="  kept  "')["environment"]["FOO"] == (
        "  kept  "
    )


def test_an_assignment_inside_a_command_stays_in_the_command() -> None:
    """Test the identifier anchor tells an assignment from a job.

    No schedule's first field can be a name followed by an equals
    sign, because a minute is counted rather than called something.
    """
    config = parse_crontab("0 2 * * * FOO=bar /usr/bin/x")

    assert config["environment"] == {}
    assert config["jobs"][0]["command"] == "FOO=bar /usr/bin/x"


def test_comments_and_blank_lines_configure_nothing() -> None:
    """Test the lines a crontab ignores are ignored here too."""
    config = parse_crontab("# a comment\n\n   \n\t# indented\n")

    assert config == {"environment": {}, "jobs": []}


@pytest.mark.parametrize(
    "line",
    [
        "not a crontab line at all",
        "run the backup every day now",
        "0 2 * * /usr/bin/too-few",
        "30 4 * * *",
        "@nosuch /usr/bin/x",
        "@reboot",
        "FOO",
        "0 2 * * mon,notaday /usr/bin/x",
    ],
)
def test_a_line_this_does_not_understand_fails(line: str) -> None:
    """Test an unreadable line stops the parse rather than vanishing.

    A crontab quietly missing a job reads as a host that does not run
    it, which is a worse answer than no answer.
    """
    with pytest.raises(ValueError, match="neither a comment"):
        parse_crontab(line)


def test_five_words_are_not_a_schedule_by_being_five() -> None:
    """Test letters are only a schedule where cron spells one.

    A minute is never named, so a word in the first three fields is a
    command that landed where a schedule belongs. Without that, any
    sentence of five words and a tail parsed as a job.
    """
    with pytest.raises(ValueError):
        parse_crontab("not a crontab line at all")

    # And the two fields cron does name still take their names
    assert parse_crontab("0 0 * dec sun /usr/bin/x")["jobs"][0][
        "schedule"
    ] == {
        "minute": "0",
        "hour": "0",
        "day": "*",
        "month": "dec",
        "weekday": "sun",
    }
