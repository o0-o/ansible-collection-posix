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

from typing import Generator

import pytest

from ansible.errors import AnsibleConnectionFailure
from ansible_collections.o0_o.posix.plugins.action.facts import ActionModule


@pytest.fixture
def plugin(base) -> Generator[ActionModule, None, None]:
    """Create an ActionModule instance with patched dependencies."""
    base._task.async_val = False
    base._task.action = "facts"

    plugin = ActionModule(
        task=base._task,
        connection=base._connection,
        play_context=base._play_context,
        loader=base._loader,
        templar=base._templar,
        shared_loader_obj=base._shared_loader_obj,
    )
    plugin._cmd = base._cmd
    plugin._display = base._display
    return plugin


def test_get_kernel_and_hardware_success(monkeypatch, plugin) -> None:
    """Test successful gathering of POSIX kernel and hardware facts."""
    monkeypatch.setattr(
        plugin,
        "_cmd",
        lambda cmd, task_vars=None, **kwargs: {
            "uname -s": {"stdout_lines": ["Linux"]},
            "uname -r": {"stdout_lines": ["6.1.0"]},
            "uname -m": {"stdout_lines": ["x86_64"]},
        }[" ".join(cmd)],
    )

    kernel, cpu = plugin._get_kernel_and_hardware(task_vars={})

    assert kernel["name"] == "linux"
    assert kernel["version"]["id"] == "6.1.0"
    assert cpu["architecture"] == "x86_64"


def test_get_kernel_and_hardware_connection_failure(monkeypatch, plugin) -> None:
    """Test that connection failures are properly propagated."""
    monkeypatch.setattr(
        plugin,
        "_cmd",
        lambda *args, **kwargs: (x for x in ()).throw(
            AnsibleConnectionFailure("connection lost")
        ),
    )

    with pytest.raises(AnsibleConnectionFailure):
        plugin._get_kernel_and_hardware(task_vars={})


def test_run_skips_on_non_posix(monkeypatch, plugin) -> None:
    """Test graceful handling of non-POSIX systems."""
    monkeypatch.setattr(
        plugin,
        "_cmd",
        lambda *args, **kwargs: (x for x in ()).throw(RuntimeError("not POSIX")),
    )

    result = plugin.run(tmp=None, task_vars={})

    assert result.get("skipped") is True
    assert "POSIX" in result.get("skip_reason", "")


@pytest.mark.parametrize(
    "subset,expect_os,expect_hw",
    [
        (["all"], True, True),
        (["kernel"], True, False),
        (["arch"], False, True),
        (["!kernel"], False, True),
    ],
)
def test_run_subset_selection(
    monkeypatch, plugin, subset, expect_os, expect_hw
) -> None:
    """Test gather_subset filtering and fact inclusion logic."""
    monkeypatch.setattr(
        plugin,
        "_cmd",
        lambda cmd, task_vars=None, **kwargs: {
            "uname -s": {"stdout_lines": ["Linux"]},
            "uname -r": {"stdout_lines": ["6.1.0"]},
            "uname -m": {"stdout_lines": ["x86_64"]},
        }[" ".join(cmd)],
    )

    plugin._task.args = {"gather_subset": subset}
    result = plugin.run(tmp=None, task_vars={})

    facts = result.get("ansible_facts", {})

    if expect_os:
        assert "o0_os" in facts
        assert facts["o0_os"]["kernel"]["name"] == "linux"
        assert {"name": "posix", "pretty": "POSIX"} in facts["o0_os"]["compliance"]
    else:
        assert "o0_os" not in facts

    if expect_hw:
        assert "o0_hardware" in facts
        assert facts["o0_hardware"]["cpu"]["architecture"] == "x86_64"
    else:
        assert "o0_hardware" not in facts
