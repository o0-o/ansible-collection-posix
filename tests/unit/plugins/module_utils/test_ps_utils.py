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

from ansible_collections.o0_o.posix.plugins.module_utils.ps_utils import (
    parse_stat,
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

    assert result["id"] == 100
    assert result["parent"] == 1
    assert result["owner"] == 1000  # Converted to int
    assert result["group"] == 1000  # Converted to int
    assert result["title"] == "/usr/sbin/sshd -D"


def test_restructure_command_with_setproctitle() -> None:
    """Test restructuring process with modified process title."""
    proc = {
        "pid": 1,
        "ppid": 0,
        "command": "sshd: /usr/sbin/sshd -D [listener]",
    }

    result = restructure_process(proc)

    # Title is kept as-is, not parsed
    assert result["title"] == "sshd: /usr/sbin/sshd -D [listener]"


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


def test_restructure_time_started_from_elapsed() -> None:
    """Test that started time is calculated from elapsed time."""
    from datetime import datetime, timedelta, timezone

    proc = {
        "pid": 100,
        "ppid": 1,
        "command": "/usr/sbin/sshd",
        "elapsed": "00:05:30",
    }

    result = restructure_process(proc)

    assert "time" in result
    assert "elapsed" in result["time"]
    assert "started" in result["time"]
    assert "seconds" in result["time"]["started"]
    assert "pretty" in result["time"]["started"]

    # Verify started is approximately 330 seconds (5:30) ago
    now = datetime.now(timezone.utc)
    started_seconds = result["time"]["started"]["seconds"]
    started_dt = datetime.fromtimestamp(started_seconds, tz=timezone.utc)
    elapsed_seconds = result["time"]["elapsed"]["seconds"]

    # Calculate expected start time
    expected_start = now - timedelta(seconds=elapsed_seconds)

    # Allow 2 second margin for test execution time
    diff = abs((started_dt - expected_start).total_seconds())
    assert diff < 2


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

    assert result["id"] == 100
    assert result["title"] == "/usr/sbin/sshd"
    # No parent, time, processor, or memory dicts
    assert "parent" in result  # Will be None
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
    assert result["owner"] == "invalid"
    assert result["group"] == "also_invalid"


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


def test_restructure_zero_rss_vsz() -> None:
    """Test a kernel thread's zeros are memory facts, not absences.

    A kernel thread holds no resident user memory and reports zero,
    which is an answer. Reading it as a column that went unanswered
    left memory_dict empty and dropped the whole memory namespace.
    """
    proc = {
        "pid": 2,
        "ppid": 0,
        "command": "[kthreadd]",
        "rss": 0,
        "vsz": 0,
        "pmem": 0.0,
    }

    result = restructure_process(proc)

    assert result["memory"]["real"]["bytes"] == 0
    assert result["memory"]["real"]["percent"] == 0.0
    assert result["memory"]["virtual"]["bytes"] == 0


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
        "pcpu": 2.5,
        "pmem": 1.2,
        "rss": 30720,
        "vsz": 102400,
    }

    result = restructure_process(proc)

    # Basic fields
    assert result["id"] == 100
    assert result["parent"] == 1
    assert result["owner"] == 1000
    assert result["group"] == 1000
    assert result["title"] == "/usr/sbin/sshd -D -f /etc/ssh/sshd_config"

    # Time fields
    assert "time" in result
    assert "elapsed" in result["time"]
    assert "started" in result["time"]
    assert "seconds" in result["time"]["started"]
    assert "pretty" in result["time"]["started"]

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


def test_parse_stat_running() -> None:
    """Test parsing running process stat."""
    stat = "R+"

    result = parse_stat(stat)

    assert result["id"] == "R+"
    assert result["state"] == "running"
    assert result["foreground"] is True
    assert result["leader"] is False
    assert result["priority"] is None


def test_parse_stat_sleeping_session_leader() -> None:
    """Test parsing sleeping session leader stat."""
    stat = "Ss"

    result = parse_stat(stat)

    assert result["id"] == "Ss"
    assert result["state"] == "sleeping"
    assert result["leader"] is True
    assert result["foreground"] is False
    assert result["multithreaded"] is False


def test_parse_stat_high_priority() -> None:
    """Test parsing high priority process stat."""
    stat = "S<"

    result = parse_stat(stat)

    assert result["id"] == "S<"
    assert result["state"] == "sleeping"
    assert result["priority"] == "high"
    assert result["locked"] is False


def test_parse_stat_low_priority() -> None:
    """Test parsing low priority process stat."""
    stat = "SN"

    result = parse_stat(stat)

    assert result["id"] == "SN"
    assert result["state"] == "sleeping"
    assert result["priority"] == "low"


def test_parse_stat_multithreaded() -> None:
    """Test parsing multithreaded process stat."""
    stat = "Sl"

    result = parse_stat(stat)

    assert result["id"] == "Sl"
    assert result["state"] == "sleeping"
    assert result["multithreaded"] is True


def test_parse_stat_locked_pages() -> None:
    """Test parsing process with locked pages."""
    stat = "SL"

    result = parse_stat(stat)

    assert result["id"] == "SL"
    assert result["state"] == "sleeping"
    assert result["locked"] is True


def test_parse_stat_zombie() -> None:
    """Test parsing zombie process stat."""
    stat = "Z"

    result = parse_stat(stat)

    assert result["id"] == "Z"
    assert result["state"] == "zombie"


def test_parse_stat_uninterruptible_bsd() -> None:
    """Test parsing uninterruptible process stat (BSD U state)."""
    stat = "U"

    result = parse_stat(stat)

    assert result["id"] == "U"
    assert result["state"] == "uninterruptible"


def test_parse_stat_exiting_bsd() -> None:
    """Test parsing exiting process stat (BSD/macOS E state)."""
    stat = "E"

    result = parse_stat(stat)

    assert result["id"] == "E"
    assert result["state"] == "exiting"


def test_parse_stat_paging_bsd() -> None:
    """Test parsing paging process stat (BSD/macOS W state)."""
    stat = "W"

    result = parse_stat(stat)

    assert result["id"] == "W"
    assert result["state"] == "paging"


def test_parse_stat_dead() -> None:
    """Test parsing dead process stat (X state)."""
    stat = "X"

    result = parse_stat(stat)

    assert result["id"] == "X"
    assert result["state"] == "dead"


def test_parse_stat_idle() -> None:
    """Test parsing idle kernel thread stat (I state)."""
    stat = "I"

    result = parse_stat(stat)

    assert result["id"] == "I"
    assert result["state"] == "idle"


def test_parse_stat_empty() -> None:
    """Test parsing empty stat field."""
    result = parse_stat("")

    assert result == {}


def test_restructure_with_stat() -> None:
    """Test restructuring process with stat field."""
    proc = {
        "pid": 100,
        "ppid": 1,
        "command": "/usr/sbin/sshd",
        "stat": "Ss",
    }

    result = restructure_process(proc)

    assert "status" in result
    assert result["status"]["id"] == "Ss"
    assert result["status"]["state"] == "sleeping"
    assert result["status"]["leader"] is True
