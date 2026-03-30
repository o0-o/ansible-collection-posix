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

"""Environment variable collection utilities.

Uses the COMMAND_SPEC pattern with dynamic ``env`` kwargs to
generate one ``printf '%s'`` command per requested variable.
The no-parser default passes stdout through unchanged; unset
variables (non-zero rc from ``set -u``) produce ``None``.
"""

from __future__ import annotations

from typing import Any

from ansible_collections.o0_o.core.plugins.module_utils import (
    process_all_command_results,
    process_command_spec,
)


def get_env_command_requests(
    env_vars: list[str],
) -> list[dict[str, Any]]:
    """Build command requests for environment variable collection.

    Generates one ``set -eu; printf '%s' "$VAR"`` request per
    variable using the COMMAND_SPEC list-expansion mechanism.

    :param list[str] env_vars: Environment variable names
    :returns list[dict[str, Any]]: Command requests for run
        plugin
    """
    from ansible_collections.o0_o.posix.plugins.module_utils.command_spec import (  # noqa: E501
        ENV_COMMAND_SPEC,
    )

    return process_command_spec(
        ENV_COMMAND_SPEC,
        cmd_type="env_var",
        env=env_vars,
    )


def process_env_command_results(
    cmds_completed: list[dict[str, Any]],
    env_vars: list[str],
    wantlist: bool = False,
    include_undefined: bool = False,
) -> Any:
    """Process env command results into structured output.

    Maps each variable to its value (from stdout).  Unset
    variables are excluded by default or included as ``None``
    when ``include_undefined`` is True.

    :param list[dict[str, Any]] cmds_completed: Command results
        from run plugin
    :param list[str] env_vars: Original variable names for
        ordering
    :param bool wantlist: Return list of single-key dicts when
        True
    :param bool include_undefined: Include unset vars as None
    :returns Any: Dict or list depending on wantlist
    """
    processed = process_all_command_results(cmds_completed)

    # env_var type may be a single dict or list of dicts
    env_results = processed.get("env_var")
    if env_results is None:
        env_results = []
    elif isinstance(env_results, dict):
        env_results = [env_results]

    # Build lookup from var name to parsed value
    values = {}
    for result in env_results:
        var_name = result.get("args", {}).get("env")
        if var_name:
            values[var_name] = result.get("parsed")

    if wantlist:
        return [
            {var: values.get(var)}
            for var in env_vars
            if include_undefined or values.get(var) is not None
        ]

    return {
        var: values.get(var)
        for var in env_vars
        if include_undefined or values.get(var) is not None
    }
