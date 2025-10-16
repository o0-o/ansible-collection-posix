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

from typing import Any, Dict, List, Union

from ansible_collections.o0_o.posix.plugins.module_utils import jc_parse
from ansible_collections.o0_o.utils.plugins.module_utils import (
    parse_datetime,
    parse_elapsed_time,
    parse_si,
)

__all__ = ["ps", "restructure_process"]


def ps(config: Union[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Process ps data - parse command output into structured format.

    Parses ps command output and restructures it with:
    - pid, ppid, uid (int), gid (int), executable, arguments
    - time dict with elapsed and started (parsed)
    - processor dict with time and percent
    - memory dict with real (bytes, pretty, percent) and virtual
      (bytes, pretty)

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
        "pid": proc.get("pid"),
        "ppid": proc.get("ppid"),
    }

    # Split command into executable and arguments string
    command = proc.get("command", "")
    if command:
        # Find first space to split executable from arguments
        space_idx = command.find(" ")
        if space_idx > 0:
            restructured["executable"] = command[:space_idx]
            restructured["arguments"] = command[space_idx + 1 :]
        else:
            # No arguments, just executable
            restructured["executable"] = command

    # Convert uid/gid to integers
    if "uid" in proc:
        try:
            restructured["uid"] = int(proc["uid"])
        except (ValueError, TypeError):
            restructured["uid"] = proc["uid"]

    if "gid" in proc:
        try:
            restructured["gid"] = int(proc["gid"])
        except (ValueError, TypeError):
            restructured["gid"] = proc["gid"]

    # Time fields
    time_dict = {}

    # time.elapsed from etime/elapsed field
    if "elapsed" in proc and proc["elapsed"]:
        elapsed_data = parse_elapsed_time(proc["elapsed"])
        if elapsed_data:
            time_dict["elapsed"] = elapsed_data
    elif "etime" in proc and proc["etime"]:
        elapsed_data = parse_elapsed_time(proc["etime"])
        if elapsed_data:
            time_dict["elapsed"] = elapsed_data

    # time.started from lstart field
    if "lstart" in proc and proc["lstart"]:
        started_data = parse_datetime(proc["lstart"])
        if started_data:
            time_dict["started"] = started_data

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
            # Add percent to real memory (pmem refers to physical memory)
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

    return restructured
