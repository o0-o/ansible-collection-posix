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

"""Unit tests for the cron action plugin.

The corpora are the live captures cron_utils is tested against, so
what the fabricated host answers with is what a real one answered.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Generator

import pytest

from ansible_collections.o0_o.posix.plugins.action.cron import ActionModule

FILES = Path(__file__).parents[1] / "module_utils" / "files"

# What the fabricated host holds, keyed the way a real one would
SYSTEM = (FILES / "crontab_etc_fedora.txt").read_text()
DROPIN = (FILES / "crontab_cron_d_fedora.txt").read_text()
ALICE = (FILES / "crontab_user_cronie.txt").read_text()

HELD = {
    "/etc/crontab": SYSTEM,
    "/etc/cron.d/0hourly": DROPIN,
    "/var/spool/cron/alice": ALICE,
}
DROPINS = ["/etc/cron.d/0hourly"]
HOLDERS = ["alice"]
UIDS = {"alice": 1000}


@pytest.fixture
def plugin(base) -> Generator[ActionModule, None, None]:
    """Create an ActionModule instance for cron tests."""
    base._task.async_val = False
    base._task.action = "cron"
    base._task.args = {}
    base._task.check_mode = False

    plugin = ActionModule(
        task=base._task,
        connection=base._connection,
        play_context=base._play_context,
        loader=base._loader,
        templar=base._templar,
        shared_loader_obj=base._shared_loader_obj,
    )
    plugin._display = base._display
    plugin.inventory_hostname = "localhost"
    return plugin


def _answer(
    monkeypatch,
    plugin: ActionModule,
    held: dict = None,
    dropins: list = None,
    holders: list = None,
    own: str = None,
    uid: str = "0",
) -> list[list[dict[str, Any]]]:
    """Answer the survey and the reads the way a real host would.

    :param monkeypatch: The pytest monkeypatch fixture
    :param ActionModule plugin: Action instance to patch
    :param dict held: The files the host holds, keyed by path
    :param list dropins: What the drop-in sweep names
    :param list holders: What the spool sweep names
    :param str own: The running identity's own crontab, or None
    :param str uid: What the host says the effective uid is
    :returns list[list[dict[str, Any]]]: The batches issued
    """
    files = HELD if held is None else held
    named = DROPINS if dropins is None else dropins
    spooled = HOLDERS if holders is None else holders
    batches: list[list[dict[str, Any]]] = []

    def mock_run(commands: Any, **kwargs: Any) -> list[dict[str, Any]]:
        batches.append(commands)
        answered = []
        for request in commands:
            kind = request["type"]

            if kind == "file":
                path = request["args"]["path"]
                content = files.get(path)
                answered.append(
                    {
                        **request,
                        "rc": 0 if content is not None else 1,
                        "stdout": content or "",
                        "stderr": "" if content else "no such file",
                    }
                )
            elif kind == "crontab_dropins":
                answered.append(
                    {**request, "rc": 0, "stdout": "\n".join(named) + "\n"}
                )
            elif kind == "crontab_spools":
                answered.append(
                    {
                        **request,
                        "rc": 0,
                        "stdout": "\n".join(spooled) + "\n",
                    }
                )
            elif kind == "crontab_self":
                answered.append(
                    {
                        **request,
                        "rc": 0 if own else 1,
                        "stdout": own or "",
                        "stderr": "" if own else "no crontab for root",
                    }
                )
            elif kind == "crontab_owner":
                name = request["args"]["user"]
                answered.append(
                    {
                        **request,
                        "rc": 0,
                        "stdout": str(UIDS.get(name, "")),
                        "stderr": "",
                    }
                )
            elif kind == "effective_uid":
                answered.append({**request, "rc": 0, "stdout": uid})
        return answered

    monkeypatch.setattr(plugin, "_run", mock_run)
    return batches


def test_a_crontab_file_is_a_fact_about_that_file(
    monkeypatch, plugin
) -> None:
    """Test the files land in the path store beside their bytes."""
    _answer(monkeypatch, plugin)

    result = plugin.run(task_vars={})
    entry = result["o0_paths"]["/etc/cron.d/0hourly"]

    assert result["changed"] is False
    assert entry["content"] == DROPIN
    assert entry["config"]["environment"]["SHELL"] == "/bin/bash"
    assert entry["config"]["jobs"][0]["user"] == "root"
    assert entry["config"]["jobs"][0]["command"] == (
        "run-parts /etc/cron.hourly"
    )
    assert entry["evidence"] == {"commands": ["cat"]}
    assert entry["origins"] == ["o0_o.posix.cron"]


def test_the_system_crontab_is_read_too(monkeypatch, plugin) -> None:
    """Test /etc/crontab is asked for without being enumerated.

    Every implementation keeps it at the same place, so it is read by
    name rather than found by a sweep.
    """
    _answer(monkeypatch, plugin)

    result = plugin.run(task_vars={})

    assert "/etc/crontab" in result["o0_paths"]
    assert result["o0_paths"]["/etc/crontab"]["config"]["jobs"] == []


def test_a_users_crontab_is_a_fact_about_that_user(
    monkeypatch, plugin
) -> None:
    """Test a spool crontab lands under the uid that owns it.

    The spool file is named for the user, and the host is asked which
    uid that is rather than a passwd file being read for it.
    """
    _answer(monkeypatch, plugin)

    result = plugin.run(task_vars={})
    entry = result["o0_users"]["1000"]

    assert entry["uid"] == 1000
    assert entry["crontab"]["environment"]["MAILTO"] == (
        "tester@example.com"
    )
    assert entry["crontab"]["jobs"][0]["schedule"] == {"special": "reboot"}
    # A per-user row names no user, so nothing here claims one
    assert all("user" not in job for job in entry["crontab"]["jobs"])
    assert entry["evidence"] == {
        "files": ["/var/spool/cron/alice"],
        "commands": ["cat"],
    }


def test_a_spool_crontab_is_not_also_a_path_entry(
    monkeypatch, plugin
) -> None:
    """Test what a spool file says is filed once, about its owner.

    It is read like any file and named under evidence, but what it
    says is a fact about the user rather than about a path a play
    would ever name.
    """
    _answer(monkeypatch, plugin)

    result = plugin.run(task_vars={})

    assert "/var/spool/cron/alice" not in result["o0_paths"]
    assert sorted(result["o0_paths"]) == [
        "/etc/cron.d/0hourly",
        "/etc/crontab",
    ]


def test_the_running_identity_reads_its_own_with_crontab(
    monkeypatch, plugin
) -> None:
    """Test the one reading POSIX defines is the one used for self."""
    _answer(monkeypatch, plugin, own=ALICE, holders=[], uid="501")

    result = plugin.run(task_vars={})
    entry = result["o0_users"]["501"]

    assert entry["uid"] == 501
    assert entry["evidence"] == {"commands": ["crontab"]}
    assert len(entry["crontab"]["jobs"]) == 6


def test_a_user_holding_no_crontab_is_null_and_not_absent(
    monkeypatch, plugin
) -> None:
    """Test asked about and not there is the store's null.

    A crontab command that answered nothing has answered: the user has
    no crontab.
    """
    _answer(monkeypatch, plugin, own=None, holders=[], uid="0")

    result = plugin.run(task_vars={})

    assert result["o0_users"]["0"]["crontab"] is None


def test_the_spools_are_swept_rather_than_the_passwd_file(
    monkeypatch, plugin
) -> None:
    """Test who holds a crontab is asked of the spools.

    This costs one command whatever the host's user count, and needs
    no other subset to have run first.
    """
    batches = _answer(monkeypatch, plugin)

    plugin.run(task_vars={})

    surveyed = [request["type"] for request in batches[0]]
    assert sorted(surveyed) == [
        "crontab_dropins",
        "crontab_self",
        "crontab_spools",
        "effective_uid",
        "file",
    ]
    # And nothing in the survey reads a passwd file
    assert all(
        request["args"]["path"] == "/etc/crontab"
        for request in batches[0]
        if request["type"] == "file"
    )


def test_every_spool_a_name_could_be_in_is_read(
    monkeypatch, plugin
) -> None:
    """Test the sweep names users and the read resolves the path.

    Which spool a crontab is in differs by implementation, and the one
    that is not there answers as absent rather than being guessed at.
    """
    batches = _answer(monkeypatch, plugin)

    plugin.run(task_vars={})

    read = [
        request["args"]["path"]
        for request in batches[1]
        if request["type"] == "file"
    ]
    assert "/var/spool/cron/alice" in read
    assert "/var/spool/cron/crontabs/alice" in read
    assert "/usr/lib/cron/tabs/alice" in read


def test_nothing_is_published_as_facts_unless_asked(
    monkeypatch, plugin
) -> None:
    """Test the returns stand alone; gather is what sets facts."""
    _answer(monkeypatch, plugin)

    result = plugin.run(task_vars={})

    assert "ansible_facts" not in result


def test_gather_publishes_the_names_a_gather_publishes(
    monkeypatch, plugin
) -> None:
    """Test the fact is the gather's shape under the gather's names."""
    _answer(monkeypatch, plugin)
    plugin._task.args = {"gather": True}

    result = plugin.run(task_vars={})
    facts = result["ansible_facts"]

    assert sorted(facts) == ["o0_paths", "o0_users"]
    assert facts["o0_paths"] == result["o0_paths"]
    assert facts["o0_users"] == result["o0_users"]


def test_a_host_with_no_cron_at_all_schedules_nothing(
    monkeypatch, plugin
) -> None:
    """Test a host without even the command answers rather than failing.

    This is what a systemd-timer host really answers: no crontab
    command, no /etc/crontab, no /etc/cron.d and no spool, every probe
    exiting non-zero having printed nothing. The absence discipline
    every sweep here follows applies - no error, a null for the
    crontab that was asked about and is not there, and evidence naming
    what was attempted.

    The shape below is what casa answered, verbatim.
    """

    def mock_run(commands: Any, **kwargs: Any) -> list[dict[str, Any]]:
        return [
            {
                **request,
                "rc": 0 if request["type"] == "effective_uid" else 127,
                "stdout": "0" if request["type"] == "effective_uid" else "",
                "stderr": "sh: crontab: command not found",
            }
            for request in commands
        ]

    monkeypatch.setattr(plugin, "_run", mock_run)

    result = plugin.run(task_vars={})

    assert result["changed"] is False
    assert result["o0_paths"] == {}
    assert result["o0_users"] == {
        "0": {
            "uid": 0,
            "crontab": None,
            "evidence": {"commands": ["crontab"]},
            "origins": ["o0_o.posix.cron"],
        }
    }


def test_a_host_with_cron_and_nothing_scheduled_says_so(
    monkeypatch, plugin
) -> None:
    """Test cron present and holding nothing is its own answer."""
    _answer(
        monkeypatch, plugin, held={}, dropins=[], holders=[], own=None
    )

    result = plugin.run(task_vars={})

    assert result["o0_paths"] == {}
    assert result["o0_users"]["0"]["crontab"] is None


def test_a_crontab_that_will_not_parse_warns_and_is_left_out(
    monkeypatch, plugin
) -> None:
    """Test one unreadable file does not take the answer with it.

    The parser is strict about a line it does not understand, and a
    module reading many files says which one defeated it rather than
    failing the task over it.
    """
    _answer(
        monkeypatch,
        plugin,
        held={
            "/etc/crontab": SYSTEM,
            "/etc/cron.d/0hourly": "this is not a crontab line\n",
        },
    )

    result = plugin.run(task_vars={})

    assert "/etc/cron.d/0hourly" not in result["o0_paths"]
    assert "/etc/crontab" in result["o0_paths"]
    assert plugin._display.warning.called
