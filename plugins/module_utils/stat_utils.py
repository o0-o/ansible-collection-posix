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

"""Portable helpers for parsing ``stat`` command output."""

from __future__ import annotations

import datetime
import stat as stat_mod
from typing import Any, Dict, List, Optional, Union

from ansible_collections.o0_o.posix.plugins.module_utils.jc_utils import (
    jc_parse,
)


def stat(config: Union[str, Dict[str, Any]]) -> Dict[str, Any]:
    """Parse stat command output into an Ansible-like structure.

    Accepts either the textual output of the ``stat`` command or a
    registered command result dictionary (for example the return value
    of ``ansible.builtin.command``). The resulting dictionary mirrors
    the keys returned by ``ansible.builtin.stat`` as closely as
    possible so callers can switch between native execution and raw
    fallback seamlessly.

    :param config: ``stat`` output as string or registered result dict
    :returns: Dictionary containing normalized stat information
    """

    if isinstance(config, dict) and config.get("rc") not in (None, 0):
        return {"exists": False}

    parsed = jc_parse("stat", config)

    # jc.parse returns a list for the stat parser. We expect a single
    # entry for the requested path.
    if isinstance(parsed, list):
        if not parsed:
            return {"exists": False}
        entry = parsed[0]
    else:
        entry = parsed

    return _normalize_stat_entry(entry)


def _normalize_stat_entry(entry: Dict[str, Any]) -> Dict[str, Any]:
    """Convert jc ``stat`` output into ansible.builtin.stat format."""

    if not entry or "file" not in entry:
        return {"exists": False}

    result: Dict[str, Any] = {
        "exists": True,
        "path": entry["file"],
    }

    result.update(_type_flags(entry))

    mode = _extract_mode(entry)
    if mode is not None:
        result["mode"] = mode
        mode_int = int(mode, 8)
        result.update(_permission_bools(mode_int))
    else:
        result["mode"] = None

    uid = _to_int(entry.get("uid"))
    gid = _to_int(entry.get("gid"))
    pw_name = entry.get("user") or None
    gr_name = entry.get("group") or None

    result.update(
        {
            "uid": uid,
            "gid": gid,
            "pw_name": pw_name,
            "gr_name": gr_name,
            "user": pw_name,
            "group": gr_name,
        }
    )

    result["size"] = _to_int(entry.get("size"))
    result["dev"] = _device_value(entry)
    result["inode"] = _to_int(entry.get("inode"))
    result["nlink"] = _to_int(entry.get("links"))
    result["rdev"] = _to_int(entry.get("rdev"))
    result["block_size"] = _to_int(entry.get("block_size"))
    result["blocks"] = _to_int(entry.get("blocks"))

    result["lnk_source"] = entry.get("link_to")

    _populate_time_fields(entry, result)

    # Extras that Ansible normally exposes but we cannot reliably
    # collect in raw mode. Populate sensible defaults so downstream
    # code does not break.
    result.setdefault("attr_flags", entry.get("unix_flags"))
    result.setdefault("xattrs", [])
    result.setdefault("selinux_label", None)

    return result


def _permission_bools(mode_int: int) -> Dict[str, bool]:
    """Derive per-bit permission booleans from an octal mode."""

    bits = {
        "isuid": bool(mode_int & stat_mod.S_ISUID),
        "isgid": bool(mode_int & stat_mod.S_ISGID),
        "isticky": bool(mode_int & stat_mod.S_ISVTX),
        "rusr": bool(mode_int & stat_mod.S_IRUSR),
        "wusr": bool(mode_int & stat_mod.S_IWUSR),
        "xusr": bool(mode_int & stat_mod.S_IXUSR),
        "rgrp": bool(mode_int & stat_mod.S_IRGRP),
        "wgrp": bool(mode_int & stat_mod.S_IWGRP),
        "xgrp": bool(mode_int & stat_mod.S_IXGRP),
        "roth": bool(mode_int & stat_mod.S_IROTH),
        "woth": bool(mode_int & stat_mod.S_IWOTH),
        "xoth": bool(mode_int & stat_mod.S_IXOTH),
    }
    return bits


def _type_flags(entry: Dict[str, Any]) -> Dict[str, bool]:
    """Return file type boolean flags."""

    file_type = (entry.get("type") or "").lower()
    flag_char = entry.get("flags", "")[:1]

    if not file_type and flag_char:
        mapping = {
            "-": "regular file",
            "d": "directory",
            "l": "symbolic link",
            "b": "block device",
            "c": "character device",
            "p": "fifo",
            "s": "socket",
        }
        file_type = mapping.get(flag_char, "")

    is_link = bool(entry.get("link_to")) or "link" in file_type

    return {
        "isdir": "directory" in file_type,
        "isreg": "regular" in file_type or (flag_char == "-" and not is_link),
        "islnk": is_link,
        "isblk": "block" in file_type,
        "ischr": "character" in file_type,
        "isfifo": "fifo" in file_type,
        "issock": "socket" in file_type,
    }


def _extract_mode(entry: Dict[str, Any]) -> Optional[str]:
    """Return the permissions mode as a zero-padded octal string."""

    access = entry.get("access")
    if access:
        try:
            return f"{int(access, 8):04o}"
        except ValueError:
            pass

    flags = entry.get("flags")
    if not flags or len(flags) < 10:
        return None

    perms = flags[1:10]
    special = 0
    if perms[2] in ("s", "S"):
        special |= 0b100
    if perms[5] in ("s", "S"):
        special |= 0b010
    if perms[8] in ("t", "T"):
        special |= 0b001

    octal_digits: List[str] = []
    for chunk in (perms[0:3], perms[3:6], perms[6:9]):
        value = 0
        if chunk[0] == "r":
            value += 4
        if chunk[1] == "w":
            value += 2
        if chunk[2] in ("x", "s", "t"):
            value += 1
        octal_digits.append(str(value))

    if special:
        return f"{special}{''.join(octal_digits)}"
    return f"0{''.join(octal_digits)}"


def _populate_time_fields(entry: Dict[str, Any], result: Dict[str, Any]) -> None:
    """Populate epoch and ISO8601 timestamps."""

    time_fields = {
        "atime": entry.get("access_time_epoch"),
        "mtime": entry.get("modify_time_epoch"),
        "ctime": entry.get("change_time_epoch"),
        "btime": entry.get("birth_time_epoch"),
    }

    for key, epoch in time_fields.items():
        if epoch is None:
            continue
        result[key] = epoch
        result[f"{key}_iso8601"] = _isoformat(epoch)


def _isoformat(epoch: Union[int, float]) -> str:
    """Convert an epoch timestamp to UTC ISO-8601 with trailing Z."""

    dt = datetime.datetime.fromtimestamp(epoch, tz=datetime.timezone.utc)
    return dt.isoformat().replace("+00:00", "Z")


def _device_value(entry: Dict[str, Any]) -> Optional[int]:
    """Attempt to derive the device number from jc output."""

    unix_device = entry.get("unix_device")
    if unix_device is not None:
        return _to_int(unix_device)

    device = entry.get("device")
    if isinstance(device, str) and "/" in device:
        suffix = device.split("/", 1)[1]
        if suffix.endswith("d"):
            suffix = suffix[:-1]
        try:
            return int(suffix, 10)
        except ValueError:
            return None
    return None


def _to_int(value: Any) -> Optional[int]:
    """Safely convert numeric strings to integers."""

    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


__all__ = ["stat"]
