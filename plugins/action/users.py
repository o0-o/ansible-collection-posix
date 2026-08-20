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

from typing import Any, Optional

from ansible.errors import AnsibleActionFail
from ansible.plugins.action import ActionBase

from ansible_collections.o0_o.posix.plugins.module_utils import (
    ReadPosixActionBase,
    compose_users_groups,
)

# The o0_o.ssh collection is an optional dependency: without it, user
# facts still gather, minus authorized_keys parsing.
try:
    from ansible_collections.o0_o.ssh.plugins.module_utils import (
        authorized_keys,
    )

    HAS_SSH_COLLECTION = True
except ImportError:
    authorized_keys = None
    HAS_SSH_COLLECTION = False


class ActionModule(ReadPosixActionBase, ActionBase):
    """Gather user and group information from POSIX hosts."""

    TRANSFERS_FILES = False
    _requires_connection = True
    _supports_check_mode = True
    _supports_async = False
    _supports_diff = False

    def run(
        self,
        tmp: Optional[str] = None,
        task_vars: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """Execute user and group fact gathering.

        :param Optional[str] tmp: Unused temporary directory path
        :param Optional[dict[str, Any]] task_vars: Available Ansible
            variables
        :returns dict[str, Any]: Result dictionary with o0_users,
            o0_groups, o0_homes, and o0_shell_files data
        """
        task_vars = task_vars or {}
        self._def_inventory_hostname(task_vars)

        result = super().run(tmp, task_vars=task_vars)
        del tmp  # unused

        argument_spec = {
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

        passwd_path = module_args["passwd_path"]
        group_path = module_args["group_path"]

        users, groups = compose_users_groups(
            self._read_text_file(passwd_path, task_vars),
            self._read_text_file(group_path, task_vars),
        )

        # Validate shells against /etc/shells if available
        self._validate_user_shells(users, task_vars)

        # Gather SSH keys for users
        self._gather_ssh_keys_for_users(users, task_vars)

        # Gather home directory metadata
        homes = self._gather_home_metadata(users, task_vars)

        # Gather shell binary metadata from user shells
        shell_files = self._gather_shell_binaries(users, task_vars)

        result.update(
            {
                "changed": False,
                "o0_users": users,
                "o0_groups": groups,
                "o0_homes": homes,
                "o0_shell_files": shell_files,
            }
        )
        return result

    def _read_text_file(self, path: str, task_vars: dict[str, Any]) -> str:
        cmd_result = self._command(
            ["cat", path], task_vars=task_vars, check_mode=False
        )
        if cmd_result.get("rc") != 0:
            error_msg = cmd_result.get("stderr") or cmd_result.get("stdout")
            raise AnsibleActionFail(f"Failed to read {path}: {error_msg}")
        return cmd_result.get("stdout", "")

    def _validate_user_shells(
        self, users: dict[str, dict[str, Any]], task_vars: dict[str, Any]
    ) -> None:
        """Validate user shells against /etc/shells if available.

        Adds 'known' boolean to each user indicating whether their
        shell is listed in /etc/shells. Requires
        config['/etc/shells'] to be populated from a previous
        facts gather.

        :param dict[str, dict[str, Any]] users: User mapping to augment
        :param dict[str, Any] task_vars: Task variables
        """
        # Check if config exists with /etc/shells data
        config = task_vars.get("config", {})
        shells_config = config.get("/etc/shells", {})
        shells_list = shells_config.get("config")

        if not shells_list or not isinstance(shells_list, list):
            # No /etc/shells config available, skip validation
            return

        # Build set of valid shells for fast lookup
        valid_shells = set(shells_list)

        # Validate each user's shell
        for user_data in users.values():
            shell = user_data.get("shell")
            if shell and isinstance(shell, str):
                user_data["known"] = shell in valid_shells

    def _gather_ssh_keys_for_users(
        self, users: dict[str, dict[str, Any]], task_vars: dict[str, Any]
    ) -> None:
        """Gather SSH keys for all users.

        Adds 'keys' dict to each user entry with 'authorized' and
        'public' keys. Handles permission issues gracefully.

        :param dict[str, dict[str, Any]] users: User mapping to augment
        :param dict[str, Any] task_vars: Task variables
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
                # No read access to .ssh directory - skip keys
                continue

            # Gather authorized keys
            auth_keys_data, auth_keys_warning = self._gather_authorized_keys(
                ssh_dir, name, task_vars
            )

            # Gather public keys
            pub_keys_data = self._gather_public_keys(ssh_dir, task_vars)

            # Only add keys dict if we have data or empty dicts
            keys: dict[str, Any] = {}
            if auth_keys_data is not None:
                keys["authorized"] = auth_keys_data
            if pub_keys_data is not None:
                keys["public"] = pub_keys_data

            if keys:
                user_data["keys"] = keys

            # Issue warning if needed
            if auth_keys_warning:
                host = self._def_inventory_hostname(task_vars)
                self._display.warning(f"[{host}] {auth_keys_warning}")

    def _check_directory_readable(
        self, path: str, task_vars: dict[str, Any]
    ) -> bool:
        """Check if a directory is readable.

        :param str path: Directory path to check
        :param dict[str, Any] task_vars: Task variables
        :returns bool: True if directory is readable
        """
        cmd_result = self._command(
            ["test", "-r", path, "-a", "-d", path],
            task_vars=task_vars,
            check_mode=False,
        )
        return cmd_result.get("rc") == 0

    def _gather_authorized_keys(
        self, ssh_dir: str, username: Optional[str], task_vars: dict[str, Any]
    ) -> tuple[Optional[dict[str, dict[str, Any]]], Optional[str]]:
        """Gather authorized_keys files for a user.

        Returns dict keyed by SSH key data with metadata about which
        file(s) contain the key. Skips gathering with a warning when
        the optional o0_o.ssh collection is not installed.

        :param str ssh_dir: Path to .ssh directory
        :param Optional[str] username: Username for warning messages
        :param dict[str, Any] task_vars: Task variables
        :returns tuple[Optional[Dict], Optional[str]]: Authorized keys
            dict (keyed by key data) and optional warning message
        """
        if not HAS_SSH_COLLECTION:
            return None, (
                "o0_o.ssh collection is not installed; skipping "
                f"authorized_keys gathering for user '{username}'"
            )

        auth_files = {
            "authorized_keys": f"{ssh_dir}/authorized_keys",
            "authorized_keys2": f"{ssh_dir}/authorized_keys2",
        }

        found_keys: dict[str, dict[str, Any]] = {}
        readable_files: list[str] = []
        unreadable_files: list[str] = []

        for key_name, file_path in auth_files.items():
            # Check if file exists and is readable
            check_cmd = self._command(
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
                            # Key exists - mark which files contain it
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
                exists_cmd = self._command(
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
        self, ssh_dir: str, task_vars: dict[str, Any]
    ) -> Optional[dict[str, dict[str, Any]]]:
        """Gather public key (.pub) files from .ssh directory.

        Returns dict keyed by SSH key data (only first line of each .pub
        file is used).

        :param str ssh_dir: Path to .ssh directory
        :param dict[str, Any] task_vars: Task variables
        :returns Optional[Dict]: Dict mapping key data to metadata, or
            None if .ssh not readable or the optional o0_o.ssh
            collection is not installed
        """
        if not HAS_SSH_COLLECTION:
            return None

        # Find all .pub files
        find_cmd = self._command(
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

        pub_keys: dict[str, dict[str, Any]] = {}
        for pub_file in pub_files:
            # Extract filename without path
            import os

            filename = os.path.basename(pub_file)

            # Try to read and parse the file (only first line)
            try:
                content = self._read_text_file(pub_file, task_vars)
                # Only use first non-empty line after trimming
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

    def _gather_home_metadata(
        self, users: dict[str, dict[str, Any]], task_vars: dict[str, Any]
    ) -> dict[str, dict[str, Any]]:
        """Gather metadata for all user home directories.

        Creates homes dict keyed by home path with file metadata and
        residents list. For symlinks, users are listed in both the
        link and target entries.

        :param dict[str, dict[str, Any]] users: User mapping
        :param dict[str, Any] task_vars: Task variables
        :returns dict[str, dict[str, Any]]: Home paths with metadata
        """
        # Collect unique home paths and build residents mapping
        home_paths = set()
        home_to_residents: dict[str, list[int]] = {}

        for user_data in users.values():
            home = user_data.get("home")
            uid = user_data.get("uid")
            if home and isinstance(home, str) and isinstance(uid, int):
                home_paths.add(home)
                if home not in home_to_residents:
                    home_to_residents[home] = []
                home_to_residents[home].append(uid)

        if not home_paths:
            return {}

        # Batch read metadata for all homes; the read action's default
        # attributes cover type, ownership, mode, timestamps, ACL, and
        # SELinux context
        read_result = self._read(
            paths=list(home_paths),
            task_vars=task_vars,
        )

        homes: dict[str, dict[str, Any]] = {}
        if not read_result.get("failed") and "paths" in read_result:
            for home_path, home_data in read_result["paths"].items():
                if home_data:
                    # Add tag and residents list
                    home_data["tags"] = ["posix", "home"]
                    home_data["residents"] = home_to_residents.get(
                        home_path, []
                    )
                    homes[home_path] = home_data

                    # For symlinks, also add residents to target
                    if (
                        home_data.get("type") == "link"
                        and "target" in home_data
                    ):
                        target = home_data["target"]
                        # Read target metadata if not already read
                        if target not in homes:
                            target_read = self._read(
                                paths=target,
                                task_vars=task_vars,
                            )
                            if (
                                not target_read.get("failed")
                                and "paths" in target_read
                            ):
                                target_data = target_read["paths"].get(target)
                                if target_data:
                                    target_data["tags"] = ["posix", "home"]
                                    target_data["residents"] = (
                                        home_to_residents.get(home_path, [])
                                    )
                                    homes[target] = target_data
                        else:
                            # Target already in homes, add residents
                            if "residents" not in homes[target]:
                                homes[target]["residents"] = []
                            homes[target]["residents"].extend(
                                home_to_residents.get(home_path, [])
                            )
                            # Remove duplicates
                            homes[target]["residents"] = list(
                                set(homes[target]["residents"])
                            )

        return homes

    def _gather_shell_binaries(
        self, users: dict[str, dict[str, Any]], task_vars: dict[str, Any]
    ) -> dict[str, dict[str, Any]]:
        """Gather metadata for shell binaries used by users.

        Creates the o0_shell_files dict keyed by shell path with file
        metadata. Only adds shells that don't already exist in
        o0_shell_files from previous facts gathering.

        :param dict[str, dict[str, Any]] users: User mapping
        :param dict[str, Any] task_vars: Task variables
        :returns dict[str, dict[str, Any]]: Shell paths with metadata
        """
        # Start with existing shell files if available
        existing_shells = task_vars.get("o0_shell_files", {})
        shells = dict(existing_shells)  # Copy to preserve existing

        # Collect unique shell paths that don't already exist
        shell_paths_to_read = set()
        for user_data in users.values():
            shell = user_data.get("shell")
            if shell and isinstance(shell, str):
                # Only gather metadata if shell not already in dict
                if shell not in shells:
                    shell_paths_to_read.add(shell)

        if not shell_paths_to_read:
            return shells

        # Batch read metadata for all new shells; the read action's
        # default attributes cover everything gathered here
        read_result = self._read(
            paths=list(shell_paths_to_read),
            task_vars=task_vars,
        )

        if not read_result.get("failed") and "paths" in read_result:
            for shell_path, shell_data in read_result["paths"].items():
                if shell_data:
                    # Add tag to identify as shell binary
                    shell_data["tags"] = ["posix", "shell"]
                    shells[shell_path] = shell_data

        return shells
