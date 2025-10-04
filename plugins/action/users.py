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

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from ansible.errors import AnsibleActionFail
from ansible.plugins.action import ActionBase

from ansible_collections.o0_o.posix.plugins.module_utils import (
    PosixActionBase,
    group_info,
    jc_parse,
    passwd_info,
)


class ActionModule(PosixActionBase, ActionBase):
    """Gather user and group information from POSIX hosts."""

    TRANSFERS_FILES = False
    _requires_connection = True
    _supports_check_mode = True
    _supports_async = False
    _supports_diff = False

    def run(
        self,
        tmp: Optional[str] = None,
        task_vars: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        task_vars = task_vars or {}
        tmp = None

        result = super().run(tmp, task_vars)

        argument_spec = {
            "key": {"type": "str", "choices": ["id", "name"], "default": "id"},
            "passwd_path": {"type": "str", "default": "/etc/passwd"},
            "group_path": {"type": "str", "default": "/etc/group"},
        }

        validation_result, module_args = self.validate_argument_spec(
            argument_spec=argument_spec
        )
        self._task.args.update(module_args)

        key = module_args["key"]
        passwd_path = module_args["passwd_path"]
        group_path = module_args["group_path"]

        passwd_content = self._read_text_file(passwd_path, task_vars)
        group_content = self._read_text_file(group_path, task_vars)

        users, groups = self._compose_user_group_maps(
            passwd_content=passwd_content,
            group_content=group_content,
            key=key,
        )

        result.update({"changed": False, "users": users, "groups": groups})
        return result

    def _read_text_file(
        self, path: str, task_vars: Dict[str, Any]
    ) -> str:
        cmd_result = self._cmd(["cat", path], task_vars=task_vars, check_mode=False)
        if cmd_result.get("rc") != 0:
            raise AnsibleActionFail(
                f"Failed to read {path}: {cmd_result.get('stderr') or cmd_result.get('stdout')}"
            )
        return cmd_result.get("stdout", "")

    def _compose_user_group_maps(
        self,
        passwd_content: str,
        group_content: str,
        key: str,
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        users_by_id = passwd_info(passwd_content, key="id")
        users_by_name = passwd_info(passwd_content, key="name")

        groups_by_id = group_info(group_content, key="id")
        groups_by_name = group_info(group_content, key="name")

        self._initialize_user_groups(users_by_id, users_by_name, groups_by_id)
        self._augment_membership(
            passwd_by_name=users_by_name,
            users_by_id=users_by_id,
            users_by_name=users_by_name,
            group_content=group_content,
            groups_by_id=groups_by_id,
            groups_by_name=groups_by_name,
        )

        if key == "id":
            return users_by_id, groups_by_id
        return users_by_name, groups_by_name

    def _initialize_user_groups(
        self,
        users_by_id: Dict[str, Dict[str, Any]],
        users_by_name: Dict[str, Dict[str, Any]],
        groups_by_id: Dict[str, Dict[str, Any]],
    ) -> None:
        for uid_str, entry in users_by_id.items():
            groups: List[int] = []
            primary_gid = entry.get("gid")
            if primary_gid is not None:
                groups.append(primary_gid)
                entry["group"] = primary_gid
            else:
                entry["group"] = None
            entry["groups"] = groups

        for name, entry in users_by_name.items():
            groups: List[str] = []
            primary_gid = entry.get("gid")
            if primary_gid is not None:
                gid_str = str(primary_gid)
                group_label = groups_by_id.get(gid_str, {}).get("name")
                if not group_label:
                    group_label = gid_str
                entry["group"] = group_label
                groups.append(group_label)
            else:
                entry["group"] = None
            entry["groups"] = groups

    def _augment_membership(
        self,
        passwd_by_name: Dict[str, Dict[str, Any]],
        users_by_id: Dict[str, Dict[str, Any]],
        users_by_name: Dict[str, Dict[str, Any]],
        group_content: str,
        groups_by_id: Dict[str, Dict[str, Any]],
        groups_by_name: Dict[str, Dict[str, Any]],
    ) -> None:
        group_entries = jc_parse("etc_group", group_content) or []

        name_to_uid: Dict[str, int] = {}
        for username, data in passwd_by_name.items():
            uid = data.get("id")
            if isinstance(uid, int):
                name_to_uid[username] = uid

        for group_entry in group_entries:
            gid = _to_int(group_entry.get("gid"))
            group_name = group_entry.get("name")
            members = group_entry.get("users") or []

            label_name = group_name or (str(gid) if gid is not None else None)

            for member in members:
                uid = name_to_uid.get(member)
                if uid is None:
                    continue
                uid_str = str(uid)
                user_id_entry = users_by_id.get(uid_str)
                if user_id_entry is not None and gid is not None:
                    if gid not in user_id_entry["groups"]:
                        user_id_entry["groups"].append(gid)

                user_name_entry = users_by_name.get(member)
                if user_name_entry is not None and label_name:
                    if label_name not in user_name_entry["groups"]:
                        user_name_entry["groups"].append(label_name)


def _to_int(value: Any) -> Optional[int]:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
