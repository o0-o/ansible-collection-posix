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

"""Unit tests for uname action plugin."""

from __future__ import annotations

from typing import Any, Generator

import pytest

from ansible_collections.o0_o.posix.plugins.action.uname import (
    ActionModule,
)
from ansible_collections.o0_o.posix.plugins.module_utils import (
    get_uname_command_requests,
    process_uname_command_results,
)

UNAME_A = (
    "Linux host 5.15.0-91-generic #101-Ubuntu SMP Tue Nov 14 13:30:08 "
    "UTC 2023 x86_64 x86_64 x86_64 GNU/Linux"
)


def _answer(output: str) -> list[dict[str, Any]]:
    """Answer the batched ``uname -a`` the way the run plugin does.

    :param str output: What the host printed
    :returns list[dict[str, Any]]: Completed command results
    """
    return [
        dict(
            request,
            rc=0,
            stdout=output,
            stdout_lines=output.splitlines(),
            stderr="",
            stderr_lines=[],
        )
        for request in get_uname_command_requests()
    ]


@pytest.fixture
def plugin(base) -> Generator[ActionModule, None, None]:
    """Create an ActionModule instance for uname tests."""
    base._task.async_val = False
    base._task.action = "uname"
    base._task.args = {}

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


def test_run_returns_what_uname_reported(monkeypatch, plugin) -> None:
    """Test the return is the shape the module documents and its own
    example reads: kernel, architecture and hostname at the top."""
    monkeypatch.setattr(
        plugin, "_run", lambda commands, **kw: _answer(UNAME_A)
    )

    result = plugin.run(task_vars={})

    assert set(result["uname"]) == {"kernel", "architecture", "hostname"}
    assert result["uname"]["kernel"]["name"] == "linux"
    assert result["uname"]["kernel"]["pretty"] == "Linux"
    assert result["uname"]["kernel"]["version"]["id"] == "5.15.0-91-generic"
    assert result["uname"]["architecture"] == "x86_64"
    assert result["uname"]["hostname"]["short"] == "host"
    assert result["changed"] is False
    assert result["msg"] == "Gathered uname facts"


def test_run_answers_like_the_filter(monkeypatch, plugin) -> None:
    """Test the module and the uname filter answer alike. The module
    used to flatten the fact namespaces instead, which put the
    architecture under a baseboard key nothing documented."""
    from ansible_collections.o0_o.posix.plugins.filter.uname import (
        FilterModule,
    )

    monkeypatch.setattr(
        plugin, "_run", lambda commands, **kw: _answer(UNAME_A)
    )

    result = plugin.run(task_vars={})

    assert result["uname"] == FilterModule().uname_filter(UNAME_A)
    assert "baseboard" not in result["uname"]


def test_gather_sorts_the_same_fields_into_namespaces() -> None:
    """Test the facts module is the one that namespaces these fields,
    from the same parse the module returns flat."""
    facts, errors = process_uname_command_results(_answer(UNAME_A))

    assert errors == []
    assert facts["o0_os"]["kernel"]["name"] == "linux"
    assert facts["o0_network"]["hostname"]["short"] == "host"
    assert facts["o0_hardware"]["baseboard"]["architecture"] == "x86_64"


def test_each_namespace_uname_feeds_names_uname() -> None:
    """Test the parser names itself on all three sections it composes.

    Origins sits where evidence sits, and this parser stamps evidence
    on each namespace it feeds, so each of them says uname composed
    part of it. The module that publishes the section names itself
    beside this one.
    """
    facts, _errors = process_uname_command_results(_answer(UNAME_A))

    for namespace in ("o0_os", "o0_network", "o0_hardware"):
        assert facts[namespace]["origins"] == ["o0_o.posix.uname"]
    # A field inside a section is not a composition of its own
    assert "origins" not in facts["o0_os"]["kernel"]


def test_each_namespace_names_the_command_that_answered_for_it() -> None:
    """Test one command answers for three namespaces and each of the
    three says so, rather than leaving a consumer of one of them to
    know the other two came out of the same invocation."""
    facts, _errors = process_uname_command_results(_answer(UNAME_A))

    for namespace in ("o0_os", "o0_network", "o0_hardware"):
        assert facts[namespace]["evidence"] == {"commands": ["uname"]}

    # Each namespace's record is its own, so writing to one of them
    # cannot rewrite another's
    facts["o0_os"]["evidence"]["commands"].append("date")
    assert facts["o0_network"]["evidence"]["commands"] == ["uname"]


def test_run_emits_warnings_on_errors(monkeypatch, plugin) -> None:
    """Test that a host whose uname says nothing warns."""
    monkeypatch.setattr(plugin, "_run", lambda commands, **kw: _answer(""))

    result = plugin.run(task_vars={})

    assert result["uname"] == {}
    plugin._display.warning.assert_called()


def test_run_calls_run_with_correct_kwargs(monkeypatch, plugin) -> None:
    """Test that _run is called with parallel and check_mode."""
    captured: dict[str, Any] = {}

    def mock_run(commands, **kwargs):
        captured.update(kwargs)
        return _answer(UNAME_A)

    monkeypatch.setattr(plugin, "_run", mock_run)

    plugin.run(task_vars={})

    assert captured["parallel"] is True
    assert captured["fail_fast"] is False
    assert captured["check_mode"] is False
