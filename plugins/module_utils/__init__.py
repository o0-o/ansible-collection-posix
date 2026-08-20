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

from ansible_collections.o0_o.posix.plugins.module_utils.df_utils import (
    df,
    parse_df,
    parse_df_entry,
)
from ansible_collections.o0_o.posix.plugins.module_utils.env_utils import (
    get_env_command_requests,
    process_env_command_results,
)
from ansible_collections.o0_o.posix.plugins.module_utils.dmidecode_utils import (  # noqa: E501
    get_dmidecode_command_requests,
    process_dmidecode_command_results,
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
from ansible_collections.o0_o.posix.plugins.module_utils.edit_utils import (
    compile_line_patterns,
    ensure_block,
    ensure_line,
    remove_block,
    remove_lines,
    render_markers,
)
from ansible_collections.o0_o.posix.plugins.module_utils.jc_utils import (
    jc_parse,
)
from ansible_collections.o0_o.posix.plugins.module_utils.dev_utils import (
    device_from_hex_major_minor,
    device_from_major_minor,
    device_value,
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
    get_mount_command_requests,
    mount,
    parse_mount,
    parse_mount_entry,
    process_mount_command_results,
)
from ansible_collections.o0_o.posix.plugins.module_utils.ps_utils import (
    ps,
    restructure_process,
)
from ansible_collections.o0_o.posix.plugins.module_utils.shells_utils import (
    parse_shells,
)

from ansible_collections.o0_o.posix.plugins.module_utils.timezone_utils import (  # noqa: E501
    get_timezone_command_requests,
    parse_timezone_offset,
    process_timezone_command_results,
)
from ansible_collections.o0_o.posix.plugins.module_utils.uptime_utils import (
    parse_uptime,
)
from ansible_collections.o0_o.posix.plugins.module_utils.who_utils import (
    parse_who,
)

# TODO: Recreate stat_utils.py - lost during restore
# from ansible_collections.o0_o.posix.plugins.module_utils.stat_utils import (
#     stat,
# )
from ansible_collections.o0_o.posix.plugins.module_utils.posix_action_base import (  # noqa: E501
    PosixActionBase,
)
from ansible_collections.o0_o.posix.plugins.module_utils.locale_utils import (
    get_locale_command_requests,
    process_locale_command_results,
)
from ansible_collections.o0_o.posix.plugins.module_utils.uname_utils import (
    get_uname_command_requests,
    process_uname_command_results,
)
from ansible_collections.o0_o.posix.plugins.module_utils.user_utils import (
    lookup_group,
    lookup_user,
)
from ansible_collections.o0_o.posix.plugins.module_utils.read_posix_action_base import (  # noqa: E501
    ReadPosixActionBase,
)
from ansible_collections.o0_o.posix.plugins.module_utils.write_posix_action_base import (  # noqa: E501
    WritePosixActionBase,
)
from ansible_collections.o0_o.posix.plugins.module_utils.compliance_utils import (  # noqa: E501
    get_compliance_command_requests,
    process_all_compliance_command_results,
)
from ansible_collections.o0_o.posix.plugins.module_utils.command_utils import (
    format_command,
    process_command_lookups,
)

__all__ = [
    "PosixActionBase",
    "ReadPosixActionBase",
    "WritePosixActionBase",
    "get_compliance_command_requests",
    "process_all_compliance_command_results",
    "format_command",
    "process_command_lookups",
    "device_from_hex_major_minor",
    "device_from_major_minor",
    "device_value",
    "df",
    "parse_df",
    "parse_df_entry",
    "get_dmidecode_command_requests",
    "process_dmidecode_command_results",
    "fstab",
    "parse_fstab",
    "parse_fstab_entry",
    "generate_fstab",
    "generate_fstab_entry",
    "hosts",
    "parse_hosts_entry",
    "generate_hosts_entry",
    "compile_line_patterns",
    "ensure_block",
    "ensure_line",
    "jc_parse",
    "remove_block",
    "remove_lines",
    "render_markers",
    "id_info",
    "group_info",
    "normalize_group_members",
    "passwd_info",
    "get_mount_command_requests",
    "mount",
    "parse_mount",
    "parse_mount_entry",
    "process_mount_command_results",
    "parse_shells",
    "get_timezone_command_requests",
    "parse_timezone_offset",
    "process_timezone_command_results",
    "parse_uptime",
    "parse_who",
    "ps",
    "restructure_process",
    # TODO: Restore stat export when stat_utils.py is recreated
    # "stat",
    "normalize_source",
    "process_registered_result",
    "get_env_command_requests",
    "get_locale_command_requests",
    "process_env_command_results",
    "process_locale_command_results",
    "get_uname_command_requests",
    "process_uname_command_results",
    "lookup_group",
    "lookup_user",
]
