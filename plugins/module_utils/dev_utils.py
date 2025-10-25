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

"""Device number conversion utilities for POSIX systems."""

from __future__ import annotations

from typing import Any, Dict, Optional


def device_from_major_minor(device_str: str) -> Optional[int]:
    """Convert Linux "major,minor" device string to device integer.

    On Linux, jc --stat returns the device field as "major,minor"
    (e.g., "254,2"). This function uses the Linux kernel formula
    to convert major/minor numbers to the device integer that
    matches ansible.builtin.stat.

    Linux uses different encoding depending on the major/minor size:
    - Legacy (major < 256, minor < 256): (major << 8) | minor
    - Modern (larger values): Complex bit-packing formula

    :param device_str: Device string in "major,minor" format
    :returns: Device number as integer, or None if parsing fails
    """
    try:
        parts = device_str.split(",")
        if len(parts) != 2:
            return None
        major = int(parts[0].strip())
        minor = int(parts[1].strip())

        # Use simple formula for common case
        if major < 256 and minor < 256:
            return (major << 8) | minor

        # Modern Linux kernel formula for larger device numbers
        return (
            ((major & 0xFFF00) << 32)
            | ((major & 0xFF) << 8)
            | ((minor & 0xFFFFFF00) << 12)
            | (minor & 0xFF)
        )
    except (ValueError, OverflowError):
        return None


def device_from_hex_major_minor(hex_str: str) -> Optional[int]:
    """Convert hex "major,minor" device string to device integer.

    The stat -c '%t,%T' format returns device numbers in
    hexadecimal. This function parses that format and uses the
    Linux kernel formula to convert major/minor numbers to the
    device integer.

    :param hex_str: Device string in hex "major,minor" format
    :returns: Device number as integer, or None if parsing fails
    """
    try:
        parts = hex_str.split(",")
        if len(parts) != 2:
            return None
        major = int(parts[0].strip(), 16)
        minor = int(parts[1].strip(), 16)

        # Use simple formula for common case
        if major < 256 and minor < 256:
            return (major << 8) | minor

        # Modern Linux kernel formula for larger device numbers
        return (
            ((major & 0xFFF00) << 32)
            | ((major & 0xFF) << 8)
            | ((minor & 0xFFFFFF00) << 12)
            | (minor & 0xFF)
        )
    except (ValueError, OverflowError):
        return None


def device_value(entry: Dict[str, Any]) -> Optional[int]:
    """Attempt to derive the device number from jc output.

    On BSD/macOS, jc provides unix_device which is already the
    st_dev integer. On Linux, jc provides device as a
    "major,minor" string which must be converted using makedev().

    :param entry: Parsed jc stat output dictionary
    :returns: Device number as integer, or None if unavailable
    """
    unix_device = entry.get("unix_device")
    if unix_device is not None:
        try:
            return int(unix_device)
        except (ValueError, TypeError):
            return None

    device = entry.get("device")

    # Linux format: "major,minor" (e.g., "254,2")
    if isinstance(device, str) and "," in device:
        dev_int = device_from_major_minor(device)
        if dev_int is not None:
            return dev_int

    # Legacy format: "disk/3d" or similar
    if isinstance(device, str) and "/" in device:
        suffix = device.split("/", 1)[1]
        if suffix.endswith("d"):
            suffix = suffix[:-1]
        try:
            return int(suffix, 10)
        except ValueError:
            return None
    return None
