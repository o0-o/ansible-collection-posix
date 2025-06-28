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

import subprocess


def real_cmd(cmd, task_vars=None, check_mode=None, **kwargs):
    """
    Execute the given command locally using subprocess and return
    a result dictionary compatible with Ansible's _cmd method.

    :param cmd: List of args or shell string
    :param task_vars: Ignored, for interface compatibility
    :param check_mode: Ignored, for interface compatibility
    :param kwargs: Catch-all to prevent breakage on extra args
    :return: dict with rc, stdout, stderr, stdout_lines, stderr_lines
    """
    if isinstance(cmd, str):
        use_shell = True
        executable = "/bin/sh"
    else:
        use_shell = False
        executable = None

    result = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        text=True,
        shell=use_shell,
        executable=executable
    )

    return {
        "rc": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "stdout_lines": result.stdout.splitlines(),
        "stderr_lines": result.stderr.splitlines(),
    }
