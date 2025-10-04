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

"""Filter wrapper for stat parsing helpers."""

from __future__ import annotations

from typing import Any, Dict

from ansible.errors import AnsibleFilterError
from ansible.module_utils.common.text.converters import to_native

from ansible_collections.o0_o.posix.plugins.module_utils import (
    stat as stat_helper,
)


DOCUMENTATION = r"""
---
name: stat
short_description: Parse stat command output
version_added: "1.5.0"
description:
  - Parse output from the C(stat) command into a structure compatible
    with what C(ansible.builtin.stat) returns.
  - Supports input provided as raw text or as a command result
    dictionary (for example, the registered output of
    C(ansible.builtin.command)).
options:
  _input:
    description:
      - Output from the C(stat) command either as a string or the
        registered result dictionary containing C(stdout).
    type: raw
    required: true
requirements:
  - jc
notes:
  - The jc library must be available on the controller.
author:
  - oØ.o (@o0-o)
"""


class FilterModule:
    """Expose the stat normalization helper as a filter."""

    def filters(self) -> Dict[str, Any]:
        """Return the available filters."""

        return {"stat": self.stat_filter}

    def stat_filter(self, config: Any) -> Dict[str, Any]:
        """Parse stat output into an ansible.builtin.stat style dict."""

        try:
            return stat_helper(config)
        except (ValueError, ImportError) as exc:
            raise AnsibleFilterError(
                f"stat failed: {type(exc).__name__}: {to_native(exc)}"
            ) from exc
