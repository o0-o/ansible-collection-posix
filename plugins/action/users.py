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
    normalize_group_members,
    passwd_info,
)
from ansible_collections.o0_o.ssh.plugins.module_utils import (
    authorized_keys,
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
            "passwd_path": {
                "type": "str",
                "default": "/etc/passwd",
                "no_log": False,
            },
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

        # Gather SSH keys for users
        self._gather_ssh_keys_for_users(users, task_vars)

        result.update({"changed": False, "users": users, "groups": groups})
        return result

    def _read_text_file(self, path: str, task_vars: Dict[str, Any]) -> str:
        cmd_result = self._cmd(
            ["cat", path], task_vars=task_vars, check_mode=False
        )
        if cmd_result.get("rc") != 0:
            error_msg = cmd_result.get("stderr") or cmd_result.get("stdout")
            raise AnsibleActionFail(f"Failed to read {path}: {error_msg}")
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

        self._initialize_user_groups(
            users_by_id=users_by_id,
            users_by_name=users_by_name,
            groups_by_id=groups_by_id,
            groups_by_name=groups_by_name,
        )
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
        groups_by_name: Dict[str, Dict[str, Any]],
    ) -> None:
        self._normalize_group_member_lists(groups_by_id, groups_by_name)

        for uid_str, entry in users_by_id.items():
            groups: List[int] = []
            primary_gid = entry.get("gid")
            if primary_gid is not None:
                groups.append(primary_gid)
                entry["group"] = primary_gid
                username = entry.get("name")
                if isinstance(username, str) and username:
                    gid_str = str(primary_gid)
                    label = (
                        groups_by_id.get(gid_str, {}).get("name") or gid_str
                    )
                    self._add_group_member(
                        groups_by_id,
                        groups_by_name,
                        primary_gid,
                        label,
                        username,
                    )
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
                self._add_group_member(
                    groups_by_id,
                    groups_by_name,
                    primary_gid,
                    group_label,
                    name,
                )
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
        group_entries = jc_parse("group", group_content) or []

        name_to_uid: Dict[str, int] = {}
        for username, data in passwd_by_name.items():
            uid = data.get("id")
            if isinstance(uid, int):
                name_to_uid[username] = uid

        for group_entry in group_entries:
            gid = _to_int(group_entry.get("gid"))
            group_name = (
                group_entry.get("name")
                or group_entry.get("group_name")
                or group_entry.get("group")
            )
            members = group_entry.get("members")
            if members is None:
                members = group_entry.get("users")
            member_names = normalize_group_members(members)

            label_name = group_name or (str(gid) if gid is not None else None)

            for member in member_names:
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

                self._add_group_member(
                    groups_by_id,
                    groups_by_name,
                    gid,
                    label_name,
                    member,
                )

    def _normalize_group_member_lists(
        self,
        groups_by_id: Dict[str, Dict[str, Any]],
        groups_by_name: Dict[str, Dict[str, Any]],
    ) -> None:
        for entry in groups_by_id.values():
            entry["members"] = normalize_group_members(entry.get("members"))

        for entry in groups_by_name.values():
            entry["members"] = normalize_group_members(entry.get("members"))

    def _add_group_member(
        self,
        groups_by_id: Dict[str, Dict[str, Any]],
        groups_by_name: Dict[str, Dict[str, Any]],
        gid: Optional[int],
        label: Optional[str],
        member: str,
    ) -> None:
        if not member:
            return

        if gid is not None:
            gid_str = str(gid)
            group_entry = groups_by_id.setdefault(gid_str, {})
            members = group_entry.get("members")
            if not isinstance(members, list):
                members = normalize_group_members(members)
                group_entry["members"] = members
            if member not in members:
                members.append(member)

        if label:
            group_entry = groups_by_name.setdefault(label, {})
            if gid is not None and "id" not in group_entry:
                group_entry["id"] = gid
            members = group_entry.get("members")
            if not isinstance(members, list):
                members = normalize_group_members(members)
                group_entry["members"] = members
            if member not in members:
                members.append(member)

    def _gather_ssh_keys_for_users(
        self, users: Dict[str, Dict[str, Any]], task_vars: Dict[str, Any]
    ) -> None:
        """Gather SSH keys for all users.

        Adds 'keys' dict to each user entry with 'authorized' and
        'public' keys. Handles permission issues gracefully.

        :param Dict[str, Dict[str, Any]] users: User mapping to augment
        :param Dict[str, Any] task_vars: Task variables
        """
        for user_key, user_data in users.items():
            home = user_data.get("home")
            name = user_data.get("name")
            if not home or not isinstance(home, str):
                continue

            ssh_dir = f"{home}/.ssh"

            # Check if we can read the .ssh directory
            can_read_ssh_dir = self._check_directory_readable(
                ssh_dir, task_vars
            )
            if not can_read_ssh_dir:
                # No read access to .ssh directory - don't add keys at all
                continue

            # Gather authorized keys
            auth_keys_data, auth_keys_warning = self._gather_authorized_keys(
                ssh_dir, name, task_vars
            )

            # Gather public keys
            pub_keys_data = self._gather_public_keys(ssh_dir, task_vars)

            # Only add keys dict if we have data or empty dicts
            keys: Dict[str, Any] = {}
            if auth_keys_data is not None:
                keys["authorized"] = auth_keys_data
            if pub_keys_data is not None:
                keys["public"] = pub_keys_data

            if keys:
                user_data["keys"] = keys

            # Issue warning if needed
            if auth_keys_warning:
                host = self._get_inventory_hostname(task_vars)
                self._display.warning(f"[{host}] {auth_keys_warning}")

    def _check_directory_readable(
        self, path: str, task_vars: Dict[str, Any]
    ) -> bool:
        """Check if a directory is readable.

        :param str path: Directory path to check
        :param Dict[str, Any] task_vars: Task variables
        :returns bool: True if directory is readable
        """
        cmd_result = self._cmd(
            ["test", "-r", path, "-a", "-d", path],
            task_vars=task_vars,
            check_mode=False,
        )
        return cmd_result.get("rc") == 0

    def _gather_authorized_keys(
        self, ssh_dir: str, username: Optional[str], task_vars: Dict[str, Any]
    ) -> Tuple[Optional[Dict[str, Dict[str, Any]]], Optional[str]]:
        """Gather authorized_keys files for a user.

        Returns dict keyed by SSH key data with metadata about which
        file(s) contain the key.

        :param str ssh_dir: Path to .ssh directory
        :param Optional[str] username: Username for warning messages
        :param Dict[str, Any] task_vars: Task variables
        :returns Tuple[Optional[Dict], Optional[str]]: Authorized keys
            dict (keyed by key data) and optional warning message
        """
        auth_files = {
            "authorized_keys": f"{ssh_dir}/authorized_keys",
            "authorized_keys2": f"{ssh_dir}/authorized_keys2",
        }

        found_keys: Dict[str, Dict[str, Any]] = {}
        readable_files: List[str] = []
        unreadable_files: List[str] = []

        for key_name, file_path in auth_files.items():
            # Check if file exists and is readable
            check_cmd = self._cmd(
                ["test", "-f", file_path, "-a", "-r", file_path],
                task_vars=task_vars,
                check_mode=False,
            )

            if check_cmd.get("rc") == 0:
                readable_files.append(key_name)
                # Read and parse the file
                try:
                    content = self._read_text_file(file_path, task_vars)
                    parsed_keys = authorized_keys(content)
                    for key_entry in parsed_keys:
                        key_data = key_entry.get("key")
                        if not key_data:
                            continue

                        # Use key data as dict key
                        if key_data in found_keys:
                            # Key already exists - mark which files it's in
                            if key_name == "authorized_keys2":
                                found_keys[key_data]["authorized_keys2"] = True
                        else:
                            # New key - add with metadata
                            found_keys[key_data] = {
                                "type": key_entry.get("type"),
                            }
                            # Only add comment if present
                            comment = key_entry.get("comment")
                            if comment:
                                found_keys[key_data]["comment"] = comment

                            if key_name == "authorized_keys2":
                                found_keys[key_data]["authorized_keys2"] = True
                            # Add options if present
                            if "options" in key_entry:
                                found_keys[key_data]["options"] = key_entry[
                                    "options"
                                ]

                except Exception:
                    # File exists but couldn't read it
                    unreadable_files.append(key_name)
                    readable_files.remove(key_name)
            else:
                # Check if file exists but is not readable
                exists_cmd = self._cmd(
                    ["test", "-f", file_path],
                    task_vars=task_vars,
                    check_mode=False,
                )
                if exists_cmd.get("rc") == 0:
                    unreadable_files.append(key_name)

        # Generate warning if we have mixed permissions
        warning = None
        if readable_files and unreadable_files:
            user_label = username or "user"
            warning = (
                f"{user_label}: SSH key information incomplete - "
                f"could read {', '.join(readable_files)} but not "
                f"{', '.join(unreadable_files)}"
            )

        # Return None if we couldn't read any authorized_keys files
        if not readable_files:
            return None, warning

        # Return empty dict if no keys found, but files were readable
        return found_keys or {}, warning

    def _gather_public_keys(
        self, ssh_dir: str, task_vars: Dict[str, Any]
    ) -> Optional[Dict[str, Dict[str, Any]]]:
        """Gather public key (.pub) files from .ssh directory.

        Returns dict keyed by SSH key data (only first line of each .pub
        file is used).

        :param str ssh_dir: Path to .ssh directory
        :param Dict[str, Any] task_vars: Task variables
        :returns Optional[Dict]: Dict mapping key data to metadata, or
            None if .ssh not readable
        """
        # Find all .pub files
        find_cmd = self._cmd(
            [
                "find",
                ssh_dir,
                "-maxdepth",
                "1",
                "-type",
                "f",
                "-name",
                "*.pub",
            ],
            task_vars=task_vars,
            check_mode=False,
        )

        if find_cmd.get("rc") != 0:
            # Could not list directory
            return None

        pub_files = [
            f.strip()
            for f in find_cmd.get("stdout", "").splitlines()
            if f.strip()
        ]

        if not pub_files:
            # No .pub files found
            return {}

        pub_keys: Dict[str, Dict[str, Any]] = {}
        for pub_file in pub_files:
            # Extract filename without path
            import os

            filename = os.path.basename(pub_file)

            # Try to read and parse the file (only first line)
            try:
                content = self._read_text_file(pub_file, task_vars)
                # Only use first non-empty line after trimming whitespace
                lines = [
                    line.strip()
                    for line in content.splitlines()
                    if line.strip()
                ]
                if not lines:
                    continue

                first_line = lines[0]
                parsed_keys = authorized_keys(first_line)
                if parsed_keys and len(parsed_keys) > 0:
                    key_entry = parsed_keys[0]
                    key_data = key_entry.get("key")
                    if key_data:
                        pub_keys[key_data] = {
                            "type": key_entry.get("type"),
                            "file": filename,
                        }
                        # Only add comment if present
                        comment = key_entry.get("comment")
                        if comment:
                            pub_keys[key_data]["comment"] = comment
            except Exception:
                # Could not read or parse this file, skip it
                continue

        return pub_keys


def _to_int(value: Any) -> Optional[int]:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
