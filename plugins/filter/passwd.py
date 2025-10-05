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

"""Filter wrapper for parsing /etc/passwd content."""

from __future__ import annotations

from typing import Any, Dict

from ansible.errors import AnsibleFilterError
from ansible.module_utils.common.text.converters import to_native

from ansible_collections.o0_o.posix.plugins.module_utils import passwd_info


DOCUMENTATION = r"""
---
name: passwd
short_description: Parse /etc/passwd content
version_added: "1.4.0"
description:
  - Parse the contents of the C(/etc/passwd) file using the jc parser
    and normalize the output into a dictionary keyed by either numeric
    user ids or user names.
options:
  _input:
    description:
      - Raw C(/etc/passwd) content, the registered result from a
        command/slurp task, or pre-parsed entries.
    type: raw
    required: true
  key:
    description:
      - Choose whether the resulting mapping is keyed by numeric user
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
    """Expose the passwd normalization helper as a filter."""

    def filters(self) -> Dict[str, Any]:
        return {"passwd": self.passwd_filter}

    def passwd_filter(
        self, config: Any, key: str = "id"
    ) -> Dict[str, Dict[str, Any]]:
        try:
            return passwd_info(config, key=key)
        except (ValueError, ImportError) as exc:
            raise AnsibleFilterError(
                f"passwd failed: {type(exc).__name__}: {to_native(exc)}"
            ) from exc
