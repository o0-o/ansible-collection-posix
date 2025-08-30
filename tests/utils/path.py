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

import os
import stat
import pwd
import grp
import uuid
import tempfile
import shutil


def generate_temp_path():
    """
    Generate a unique temporary file or directory path.

    This does NOT touch the disk. The caller is responsible for creating
    the file or directory. You can clean up manually or use
    `cleanup_path(path)` after the test.
    """
    base_dir = tempfile.gettempdir()
    unique_name = f"temp_{uuid.uuid4().hex}"
    return os.path.join(base_dir, unique_name)


def cleanup_path(path):
    """
    Clean up a path by removing the file or directory.

    Removes directories recursively or deletes files. Ignores missing
    paths.
    """
    if os.path.isdir(path):
        shutil.rmtree(path, ignore_errors=True)
    elif os.path.isfile(path):
        os.remove(path)


def check_path_mode(path, perms):
    """
    Check that the file at `path` has the expected mode from `perms`.

    Args:
        path (str): The path to the file or directory.
        perms (dict): Dict with "mode" key as octal string.
    """
    if "mode" in perms:
        actual_mode = stat.S_IMODE(os.stat(path).st_mode)
        expected_mode = int(perms["mode"], 8)
        assert (
            actual_mode == expected_mode
        ), f"Expected mode {expected_mode:o}, got {actual_mode:o}"


def check_path_ownership(path, perms):
    """
    Check that the file at `path` has the expected owner and/or group.

    Args:
        path (str): The path to the file or directory.
        perms (dict): Dict with optional "owner" and/or "group" keys.
    """
    stat_result = os.stat(path)

    if "owner" in perms:
        expected_uid = pwd.getpwnam(perms["owner"]).pw_uid
        assert (
            stat_result.st_uid == expected_uid
        ), f"Expected uid {expected_uid}, got {stat_result.st_uid}"

    if "group" in perms:
        expected_gid = grp.getgrnam(perms["group"]).gr_gid
        assert (
            stat_result.st_gid == expected_gid
        ), f"Expected gid {expected_gid}, got {stat_result.st_gid}"
