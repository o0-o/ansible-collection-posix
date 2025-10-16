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

import pytest

from ansible_collections.o0_o.posix.plugins.module_utils.ps_utils import (
    restructure_process,
)


def test_restructure_basic_fields() -> None:
    """Test restructuring basic process fields."""
    proc = {
        "pid": 100,
        "ppid": 1,
        "uid": "1000",
        "gid": "1000",
        "command": "/usr/sbin/sshd -D",
    }

    result = restructure_process(proc)

    assert result["pid"] == 100
    assert result["ppid"] == 1
    assert result["uid"] == 1000  # Converted to int
    assert result["gid"] == 1000  # Converted to int
    assert result["executable"] == "/usr/sbin/sshd"
    assert result["arguments"] == "-D"


def test_restructure_command_no_arguments() -> None:
    """Test restructuring process with no arguments."""
    proc = {"pid": 1, "ppid": 0, "command": "/sbin/init"}

    result = restructure_process(proc)

    assert result["executable"] == "/sbin/init"
    assert "arguments" not in result


def test_restructure_time_elapsed() -> None:
    """Test restructuring time.elapsed field."""
    proc = {
        "pid": 100,
        "ppid": 1,
        "command": "/usr/sbin/sshd",
        "elapsed": "2-03:45:12",
    }

    result = restructure_process(proc)

    assert "time" in result
    assert "elapsed" in result["time"]
    assert result["time"]["elapsed"]["seconds"] == 186312
    assert (
        result["time"]["elapsed"]["pretty"]
        == "2 days, 3 hours, 45 minutes, 12 seconds"
    )
    assert result["time"]["elapsed"]["iso8601"] == "P2DT3H45M12S"


def test_restructure_time_started() -> None:
    """Test restructuring time.started field."""
    proc = {
        "pid": 100,
        "ppid": 1,
        "command": "/usr/sbin/sshd",
        "lstart": "Mon Jan  1 12:00:00 2025",
    }

    result = restructure_process(proc)

    assert "time" in result
    assert "started" in result["time"]
    assert "seconds" in result["time"]["started"]
    assert "iso8601" in result["time"]["started"]


def test_restructure_processor_time() -> None:
    """Test restructuring processor.time field."""
    proc = {
        "pid": 100,
        "ppid": 1,
        "command": "/usr/sbin/sshd",
        "time": "01:23:45",
    }

    result = restructure_process(proc)

    assert "processor" in result
    assert "time" in result["processor"]
    assert result["processor"]["time"]["seconds"] == 5025
    assert "pretty" in result["processor"]["time"]
    assert "iso8601" in result["processor"]["time"]


def test_restructure_processor_percent() -> None:
    """Test restructuring processor.percent field."""
    proc = {
        "pid": 100,
        "ppid": 1,
        "command": "/usr/sbin/sshd",
        "pcpu": 2.5,
    }

    result = restructure_process(proc)

    assert "processor" in result
    assert result["processor"]["percent"] == 2.5


def test_restructure_processor_percent_cpu_percent() -> None:
    """Test processor.percent from cpu_percent field."""
    proc = {
        "pid": 100,
        "ppid": 1,
        "command": "/usr/sbin/sshd",
        "cpu_percent": 3.2,
    }

    result = restructure_process(proc)

    assert "processor" in result
    assert result["processor"]["percent"] == 3.2


def test_restructure_memory_real() -> None:
    """Test restructuring memory.real field."""
    proc = {
        "pid": 100,
        "ppid": 1,
        "command": "/usr/sbin/sshd",
        "rss": 30720,
        "pmem": 1.2,
    }

    result = restructure_process(proc)

    assert "memory" in result
    assert "real" in result["memory"]
    assert result["memory"]["real"]["bytes"] == 31457280  # 30720 * 1024
    assert "pretty" in result["memory"]["real"]
    assert result["memory"]["real"]["percent"] == 1.2


def test_restructure_memory_virtual() -> None:
    """Test restructuring memory.virtual field."""
    proc = {
        "pid": 100,
        "ppid": 1,
        "command": "/usr/sbin/sshd",
        "vsz": 102400,
    }

    result = restructure_process(proc)

    assert "memory" in result
    assert "virtual" in result["memory"]
    assert result["memory"]["virtual"]["bytes"] == 104857600  # 102400 * 1024
    assert "pretty" in result["memory"]["virtual"]


def test_restructure_minimal_process() -> None:
    """Test restructuring process with minimal fields."""
    proc = {"pid": 100, "command": "/usr/sbin/sshd"}

    result = restructure_process(proc)

    assert result["pid"] == 100
    assert result["executable"] == "/usr/sbin/sshd"
    # No ppid, time, processor, or memory dicts
    assert "ppid" in result  # Will be None
    assert "time" not in result
    assert "processor" not in result
    assert "memory" not in result


def test_restructure_invalid_uid_gid() -> None:
    """Test handling invalid uid/gid values."""
    proc = {
        "pid": 100,
        "ppid": 1,
        "uid": "invalid",
        "gid": "also_invalid",
        "command": "/usr/sbin/sshd",
    }

    result = restructure_process(proc)

    # Should keep original values if conversion fails
    assert result["uid"] == "invalid"
    assert result["gid"] == "also_invalid"


def test_restructure_empty_elapsed() -> None:
    """Test handling empty elapsed field."""
    proc = {
        "pid": 100,
        "ppid": 1,
        "command": "/usr/sbin/sshd",
        "elapsed": "",
    }

    result = restructure_process(proc)

    # Should not include time dict if parsing fails
    assert "time" not in result


def test_restructure_empty_rss_vsz() -> None:
    """Test handling empty rss/vsz fields."""
    proc = {
        "pid": 100,
        "ppid": 1,
        "command": "/usr/sbin/sshd",
        "rss": None,
        "vsz": None,
    }

    result = restructure_process(proc)

    # Should not include memory dict if no valid values
    assert "memory" not in result


def test_restructure_complete_process() -> None:
    """Test restructuring process with all fields."""
    proc = {
        "pid": 100,
        "ppid": 1,
        "uid": "1000",
        "gid": "1000",
        "command": "/usr/sbin/sshd -D -f /etc/ssh/sshd_config",
        "elapsed": "2-03:45:12",
        "time": "01:23:45",
        "lstart": "Mon Jan  1 12:00:00 2025",
        "pcpu": 2.5,
        "pmem": 1.2,
        "rss": 30720,
        "vsz": 102400,
    }

    result = restructure_process(proc)

    # Basic fields
    assert result["pid"] == 100
    assert result["ppid"] == 1
    assert result["uid"] == 1000
    assert result["gid"] == 1000
    assert result["executable"] == "/usr/sbin/sshd"
    assert result["arguments"] == "-D -f /etc/ssh/sshd_config"

    # Time fields
    assert "time" in result
    assert "elapsed" in result["time"]
    assert "started" in result["time"]

    # Processor fields
    assert "processor" in result
    assert "time" in result["processor"]
    assert "percent" in result["processor"]

    # Memory fields
    assert "memory" in result
    assert "real" in result["memory"]
    assert "virtual" in result["memory"]
    assert "percent" in result["memory"]["real"]


def test_restructure_mem_percent_vs_pmem() -> None:
    """Test that mem_percent takes precedence over pmem."""
    proc = {
        "pid": 100,
        "ppid": 1,
        "command": "/usr/sbin/sshd",
        "rss": 30720,
        "mem_percent": 1.5,
        "pmem": 1.2,
    }

    result = restructure_process(proc)

    assert result["memory"]["real"]["percent"] == 1.5


def test_restructure_etime_vs_elapsed() -> None:
    """Test that elapsed field takes precedence over etime."""
    proc = {
        "pid": 100,
        "ppid": 1,
        "command": "/usr/sbin/sshd",
        "elapsed": "1-00:00:00",
        "etime": "2-00:00:00",
    }

    result = restructure_process(proc)

    # elapsed field should be used (86400 seconds = 1 day)
    assert result["time"]["elapsed"]["seconds"] == 86400
