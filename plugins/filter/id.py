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

"""Filter wrapper for parsing id command output."""

from __future__ import annotations

from typing import Any

from ansible.errors import AnsibleFilterError
from ansible.module_utils.common.text.converters import to_native

from ansible_collections.o0_o.posix.plugins.module_utils import id_info

DOCUMENTATION = r"""
---
name: id
short_description: Parse id command output
version_added: "2.0.0"
description:
  - Parse output from the C(id) command using the jc parser and
    normalize it into user/group mappings that can be keyed by numeric
    ids or by names.
options:
  _input:
    description:
      - Output from the C(id) command either as text or as a registered
        result dictionary containing C(stdout).
    type: raw
    required: true
  key:
    description:
      - Select whether the resulting dictionaries are keyed by numeric
        ids or by names.
    type: str
    choices: [id, name]
    default: id
requirements:
  - jc
notes:
  - The jc library must be available on the controller.
author:
  - oØ.o (@o0-o)
"""


class FilterModule:
    """Expose the id normalization helper as a filter."""

    def filters(self) -> dict[str, Any]:
        return {"id": self.id_filter}

    def id_filter(self, config: Any, key: str = "id") -> dict[str, Any]:
        try:
            return id_info(config, key=key)
        except (ValueError, ImportError) as exc:
            raise AnsibleFilterError(
                f"id failed: {type(exc).__name__}: {to_native(exc)}"
            ) from exc
