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

"""Filter wrapper for parsing /etc/shells content."""

from __future__ import annotations

from typing import Any, Dict, List, Sequence, Union

from ansible.errors import AnsibleFilterError
from ansible.module_utils.common.text.converters import to_native

from ansible_collections.o0_o.posix.plugins.module_utils import parse_shells


DOCUMENTATION = r"""
---
name: shells
short_description: Parse /etc/shells content
version_added: "1.4.0"
description:
  - Parse the contents of the C(/etc/shells) file into a list of valid
    login shell paths.
  - Strips comments and blank lines automatically.
  - Accepts raw strings, command output, or slurp results.
options:
  _input:
    description:
      - Raw C(/etc/shells) content, the registered result from a
        command/slurp task, or an iterable of lines.
    type: raw
    required: true
notes:
  - Comment lines starting with C(#) are automatically stripped.
  - Blank lines and trailing comments are ignored.
author:
  - oØ.o (@o0-o)
"""

EXAMPLES = r"""
# Parse /etc/shells from slurp
- name: Read /etc/shells
  ansible.builtin.slurp:
    src: /etc/shells
  register: shells_slurp

- name: Parse shells
  ansible.builtin.set_fact:
    valid_shells: "{{ shells_slurp | o0_o.posix.shells }}"

# Parse from command output
- name: Get shells via cat
  ansible.builtin.command:
    cmd: cat /etc/shells
  register: shells_cmd

- name: Parse shells
  ansible.builtin.set_fact:
    valid_shells: "{{ shells_cmd | o0_o.posix.shells }}"

# Parse from raw string
- name: Parse shells from variable
  ansible.builtin.set_fact:
    valid_shells: "{{ shells_content | o0_o.posix.shells }}"
  vars:
    shells_content: |
      # Valid login shells
      /bin/sh
      /bin/bash
      /bin/zsh
"""

RETURN = r"""
_value:
  description: List of valid login shell paths
  type: list
  elements: str
  sample:
    - /bin/sh
    - /bin/bash
    - /bin/dash
    - /bin/zsh
"""


class FilterModule:
    """Expose the shells parsing helper as a filter."""

    def filters(self) -> Dict[str, Any]:
        """Return the filter functions."""
        return {"shells": self.shells_filter}

    def shells_filter(
        self,
        config: Union[str, Sequence[str], Dict[str, Any]],
    ) -> List[str]:
        """Parse /etc/shells content into list of shell paths.

        Parses /etc/shells content, stripping comments and blank
        lines to return a list of valid login shell paths.

        :param config: /etc/shells content as string or dict
        :returns: List of shell paths
        :raises AnsibleFilterError: If parsing fails
        """
        try:
            return parse_shells(config)
        except (ValueError, ImportError) as e:
            raise AnsibleFilterError(
                f"shells failed: {type(e).__name__}: {to_native(e)}"
            ) from e
