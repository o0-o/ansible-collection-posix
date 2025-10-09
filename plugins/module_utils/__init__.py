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

"""Module utilities for the o0_o.posix collection."""

from __future__ import annotations

from ansible_collections.o0_o.posix.plugins.module_utils.authorized_keys_utils import (  # noqa: E501
    authorized_keys,
    parse_authorized_keys,
    parse_authorized_keys_entry,
)
from ansible_collections.o0_o.posix.plugins.module_utils.df_utils import (
    df,
    parse_df,
    parse_df_entry,
)
from ansible_collections.o0_o.posix.plugins.module_utils.dmidecode_utils import (
    dmidecode,
)
from ansible_collections.o0_o.posix.plugins.module_utils.filter_utils import (
    normalize_source,
    process_registered_result,
)
from ansible_collections.o0_o.posix.plugins.module_utils.fstab_utils import (
    fstab,
    parse_fstab,
    parse_fstab_entry,
    generate_fstab,
    generate_fstab_entry,
)
from ansible_collections.o0_o.posix.plugins.module_utils.jc_utils import (
    jc_parse,
)
from ansible_collections.o0_o.posix.plugins.module_utils.compliance_utils import (  # noqa: E501
    is_posix,
)
from ansible_collections.o0_o.posix.plugins.module_utils.id_utils import (
    id_info,
)
from ansible_collections.o0_o.posix.plugins.module_utils.group_utils import (
    group_info,
    normalize_group_members,
)
from ansible_collections.o0_o.posix.plugins.module_utils.hosts_utils import (
    hosts,
    parse_hosts_entry,
    generate_hosts_entry,
)
from ansible_collections.o0_o.posix.plugins.module_utils.passwd_utils import (
    passwd_info,
)
from ansible_collections.o0_o.posix.plugins.module_utils.mount_utils import (
    mount,
    parse_mount,
    parse_mount_entry,
)
from ansible_collections.o0_o.posix.plugins.module_utils.stat_utils import (
    stat,
)
from ansible_collections.o0_o.posix.plugins.module_utils.posix_action_base import (  # noqa: E501
    PosixActionBase,
)
from ansible_collections.o0_o.posix.plugins.module_utils.uname_utils import (
    uname,
)

__all__ = [
    "PosixActionBase",
    "authorized_keys",
    "parse_authorized_keys",
    "parse_authorized_keys_entry",
    "df",
    "parse_df",
    "parse_df_entry",
    "dmidecode",
    "fstab",
    "parse_fstab",
    "parse_fstab_entry",
    "generate_fstab",
    "generate_fstab_entry",
    "hosts",
    "parse_hosts_entry",
    "generate_hosts_entry",
    "jc_parse",
    "is_posix",
    "id_info",
    "group_info",
    "normalize_group_members",
    "passwd_info",
    "mount",
    "parse_mount",
    "parse_mount_entry",
    "stat",
    "normalize_source",
    "process_registered_result",
    "uname",
]
