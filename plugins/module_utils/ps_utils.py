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

from datetime import datetime, timedelta
from typing import Any, Dict, List, Union

from ansible_collections.o0_o.posix.plugins.module_utils import jc_parse
from ansible_collections.o0_o.utils.plugins.module_utils import (
    parse_datetime,
    parse_elapsed_time,
    parse_si,
)

__all__ = ["ps", "restructure_process", "parse_stat"]


def parse_stat(stat_str: str) -> Dict[str, Any]:
    """Parse ps stat field into structured status information.

    The stat field contains a multi-character code indicating the
    process state. Format varies between BSD and Linux but generally:
    - First char: state (R/S/D/T/Z/I/U/E/W/X)
    - Additional chars: modifiers (s=session leader, +=foreground,
      <>=priority, L=locked pages, etc.)

    States:
    - R: Running - executing or runnable (ready to run)
    - S: Sleeping - waiting for event/interruptible sleep
    - D: Uninterruptible sleep - waiting on I/O, cannot be signaled
    - T: Stopped - suspended (SIGSTOP, job control, or traced)
    - Z: Zombie - terminated, waiting for parent wait()
    - I: Idle - kernel thread idle (Linux)
    - U: Uninterruptible (BSD) - equivalent to Linux D
    - E: Exiting (BSD/macOS) - about to terminate
    - W: Paging (BSD/macOS) - waiting for paging I/O
    - X: Dead - defunct/shouldn't appear (rare internal state)

    :param str stat_str: Raw stat field from ps
    :returns Dict[str, Any]: Structured status information
    """
    if not stat_str:
        return {}

    status = {"id": stat_str}

    # First character is the state
    state_char = stat_str[0]
    state_map = {
        "R": "running",
        "S": "sleeping",
        "D": "uninterruptible",
        "T": "stopped",
        "Z": "zombie",
        "I": "idle",
        "U": "uninterruptible",  # BSD equivalent to D
        "E": "exiting",  # BSD/macOS
        "W": "paging",  # BSD/macOS
        "X": "dead",
    }
    status["state"] = state_map.get(state_char, "unknown")

    # Parse modifiers
    status["leader"] = "s" in stat_str  # Session leader
    status["multithreaded"] = "l" in stat_str  # Multi-threaded (BSD)
    status["foreground"] = "+" in stat_str  # Foreground process group

    # Priority
    if "<" in stat_str:
        status["priority"] = "high"
    elif "N" in stat_str:
        status["priority"] = "low"
    else:
        status["priority"] = None

    # Locked pages in memory
    status["locked"] = "L" in stat_str

    return status


def ps(config: Union[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Process ps data - parse command output into structured format.

    Parses ps command output and restructures it with:
    - id, parent, user (int), group (int), title (full process title)
    - status dict with:
        - id: raw stat string
        - state: running, sleeping, uninterruptible, stopped, zombie,
          idle, exiting, paging, dead
        - leader: session leader flag
        - multithreaded: multi-threaded process flag
        - foreground: foreground process group flag
        - priority: high, low, or None
        - locked: has locked pages in memory
    - time dict with elapsed (parsed) and started (calculated from
      elapsed)
    - processor dict with time and percent
    - memory dict with real (bytes, pretty, percent) and virtual
      (bytes, pretty)

    Note: The title field is kept as-is and not split into
    executable/arguments because processes can modify their process
    title via setproctitle().

    :param config: ps command output as string or command result dict
    :returns: List of process dicts with restructured fields
    :raises ValueError: If parsing fails
    :raises ImportError: If jc library not available
    """
    # Parse with jc
    parsed_processes = jc_parse("ps", config)

    # Restructure each process
    restructured_processes = []
    for proc in parsed_processes:
        restructured = restructure_process(proc)
        restructured_processes.append(restructured)

    return restructured_processes


def restructure_process(proc: Dict[str, Any]) -> Dict[str, Any]:
    """Restructure process dict with organized and parsed fields.

    :param Dict[str, Any] proc: Raw process dict from jc
    :returns Dict[str, Any]: Restructured process dict
    """
    restructured = {
        "id": proc.get("pid"),
        "parent": proc.get("ppid"),
    }

    # Keep full command as-is (don't try to split into executable/args)
    # Processes can set this to anything via setproctitle(), so parsing
    # it into separate fields is unreliable
    title = proc.get("command", "")
    if title:
        restructured["title"] = title

    # Convert uid/gid to integers (use "owner" to match file metadata)
    if "uid" in proc:
        try:
            restructured["owner"] = int(proc["uid"])
        except (ValueError, TypeError):
            restructured["owner"] = proc["uid"]

    if "gid" in proc:
        try:
            restructured["group"] = int(proc["gid"])
        except (ValueError, TypeError):
            restructured["group"] = proc["gid"]

    # Time fields
    time_dict = {}

    # time.elapsed from etime/elapsed field
    elapsed_data = None
    if "elapsed" in proc and proc["elapsed"]:
        elapsed_data = parse_elapsed_time(proc["elapsed"])
        if elapsed_data:
            time_dict["elapsed"] = elapsed_data
    elif "etime" in proc and proc["etime"]:
        elapsed_data = parse_elapsed_time(proc["etime"])
        if elapsed_data:
            time_dict["elapsed"] = elapsed_data

    # Calculate started time from elapsed time
    # (lstart field is no longer used because it contains spaces
    # which breaks jc parsing of ps output)
    if elapsed_data and "seconds" in elapsed_data:
        # Use local timezone so offset and pretty fields reflect localhost
        # Truncate microseconds since elapsed is second-precision
        now = datetime.now().astimezone().replace(microsecond=0)
        started_dt = now - timedelta(seconds=elapsed_data["seconds"])
        # Format as ISO8601 and parse back to get consistent structure
        started_str = started_dt.isoformat()
        started_parsed = parse_datetime(started_str)
        if started_parsed:
            time_dict["started"] = started_parsed

    if time_dict:
        restructured["time"] = time_dict

    # Processor fields
    processor_dict = {}

    # processor.time from time field (CPU time consumed)
    if "time" in proc and proc["time"]:
        processor_time_data = parse_elapsed_time(proc["time"])
        if processor_time_data:
            processor_dict["time"] = processor_time_data

    # processor.percent from pcpu/cpu_percent field
    if "cpu_percent" in proc:
        processor_dict["percent"] = proc["cpu_percent"]
    elif "pcpu" in proc:
        processor_dict["percent"] = proc["pcpu"]

    if processor_dict:
        restructured["processor"] = processor_dict

    # Memory fields
    memory_dict = {}

    # memory.real from rss field (with SI parsing)
    # ps reports rss in kilobytes on most systems
    if "rss" in proc and proc["rss"]:
        rss_value = f"{proc['rss']}K"
        rss_data = parse_si(rss_value, binary=True)
        if rss_data:
            real_dict = rss_data.copy()
            # Add percent to real (pmem = physical memory)
            if "mem_percent" in proc:
                real_dict["percent"] = proc["mem_percent"]
            elif "pmem" in proc:
                real_dict["percent"] = proc["pmem"]
            memory_dict["real"] = real_dict

    # memory.virtual from vsz field (with SI parsing)
    # ps reports vsz in kilobytes on most systems
    if "vsz" in proc and proc["vsz"]:
        vsz_value = f"{proc['vsz']}K"
        vsz_data = parse_si(vsz_value, binary=True)
        if vsz_data:
            memory_dict["virtual"] = vsz_data

    if memory_dict:
        restructured["memory"] = memory_dict

    # Parse stat field into status dict
    if "stat" in proc and proc["stat"]:
        status = parse_stat(proc["stat"])
        if status:
            restructured["status"] = status

    return restructured
