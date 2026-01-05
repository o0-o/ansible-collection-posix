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

"""Path and permission utilities for POSIX action plugins.

Standalone functions for parsing file permissions and other path-related
operations. These functions are designed to be used independently of
ActionBase classes.
"""

from __future__ import annotations


def flags_to_octal_mode(flags: str) -> str:
    """Convert ls permission flags to octal mode string.

    Parses the 10-character permission string from ls output
    (e.g., "-rwxr-xr-x") and converts it to a 4-digit octal
    mode string (e.g., "0755").

    :param str flags: Permission flags from ls (10 characters)
    :returns str: Octal mode as 4-digit string (e.g., "0755")
    """
    if not flags or len(flags) < 10:
        return "0000"

    perms = flags[1:]  # Skip first char (file type)
    octal = 0

    # Owner permissions
    if perms[0] == "r":
        octal += 0o400
    if perms[1] == "w":
        octal += 0o200
    if perms[2] in ["x", "s", "S"]:
        octal += 0o100
    if perms[2] in ["s", "S"]:
        octal += 0o4000  # setuid

    # Group permissions
    if perms[3] == "r":
        octal += 0o040
    if perms[4] == "w":
        octal += 0o020
    if perms[5] in ["x", "s", "S"]:
        octal += 0o010
    if perms[5] in ["s", "S"]:
        octal += 0o2000  # setgid

    # Other permissions
    if perms[6] == "r":
        octal += 0o004
    if perms[7] == "w":
        octal += 0o002
    if perms[8] in ["x", "t", "T"]:
        octal += 0o001
    if perms[8] in ["t", "T"]:
        octal += 0o1000  # sticky bit

    return f"{octal:04o}"
