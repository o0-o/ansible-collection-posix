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

from ansible.errors import AnsibleError
import subprocess


def real_cmd(cmd, stdin=None, task_vars=None, check_mode=None, **kwargs):
    """
    Simulate the fallback _command logic using real subprocess
    execution. Supports both list and string commands, and optional
    stdin input. Under check mode nothing is executed and a no-op
    success result is returned, so check-mode assertions are real.
    """
    if isinstance(cmd, list):
        shell = False
    elif isinstance(cmd, str):
        shell = True
    else:
        raise TypeError(
            f"Expected cmd to be str or list, got {type(cmd).__name__}"
        )

    if check_mode:
        return {
            "rc": 0,
            "stdout": "",
            "stderr": "",
            "stdout_lines": [],
            "stderr_lines": [],
            "cmd": cmd,
            "check_mode": True,
        }

    try:
        result = subprocess.run(
            cmd,
            input=stdin.encode("utf-8") if stdin else None,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=shell,
            check=False,
        )
        return {
            "rc": result.returncode,
            "stdout": result.stdout.decode("utf-8"),
            "stderr": result.stderr.decode("utf-8"),
            "stdout_lines": result.stdout.decode("utf-8").splitlines(),
            "stderr_lines": result.stderr.decode("utf-8").splitlines(),
            "cmd": cmd,
        }
    except Exception as e:
        raise AnsibleError(f"real_cmd failed: {e}")
