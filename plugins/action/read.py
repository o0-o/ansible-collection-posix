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

from os.path import dirname, isabs, join, normpath
from typing import Any, Optional

from ansible.errors import AnsibleActionFail
from ansible.plugins.action import ActionBase

from ansible_collections.o0_o.posix.plugins.module_utils import (
    ReadPosixActionBase,
)
from ansible_collections.o0_o.utils.plugins.module_utils import (
    truthy_or_integer,
    truthy_or_string,
)


class ActionModule(ReadPosixActionBase, ActionBase):
    """Minimal read module demonstrating clean batched architecture."""

    TRANSFERS_FILES = False
    _requires_connection = True
    _supports_check_mode = True
    _supports_async = False
    _supports_diff = False

    def _display_longest_command(
        self, commands_result: dict[str, Any], context: str = ""
    ) -> None:
        """Display debug information about the longest running command.

        :param dict commands_result: Result from _run() call
        :param str context: Context description for the debug message
        """
        if not isinstance(commands_result.get("commands"), dict):
            return

        # Find the longest running command
        longest_cmd = None
        longest_elapsed = 0

        for cmd_key, cmd_result in commands_result["commands"].items():
            if "elapsed" in cmd_result:
                elapsed = cmd_result["elapsed"].get("seconds", 0)
                if elapsed > longest_elapsed:
                    longest_elapsed = elapsed
                    longest_cmd = cmd_result.get("cmd", cmd_key)

        context_str = f" ({context})" if context else ""
        if longest_elapsed > 0:
            self._display.vvv(
                f"[{self.inventory_hostname}] Longest command{context_str}: "
                f"{longest_cmd} took {longest_elapsed}s"
            )
        else:
            self._display.vvv(
                f"[{self.inventory_hostname}] All commands{context_str} "
                f"completed in under 1 second"
            )

    def _def_args(self) -> dict[str, Any]:
        """Parse and validate module arguments."""
        argument_spec = {
            "paths": {
                "type": "list",
                "required": True,
                "elements": "str",
                "aliases": ["path"],
                "description": "Path or list of paths to inspect",
            },
            "metadata": {
                "type": "bool",
                "default": True,
                "description": (
                    "Include basic metadata and extended filesystem "
                    "attributes: type, mode, owner, group, size, writable, "
                    "hardlinks, inode, timestamps (modified, created, "
                    "changed), ACL, filesystem flags, and SELinux context "
                    "(but NOT xattrs)"
                ),
            },
            "extended": {
                "type": "bool",
                "default": False,
                "description": (
                    "Include extended attributes (xattrs). "
                    "Implies metadata=true"
                ),
            },
            "content": {
                "type": "bool",
                "default": False,
                "description": "Include file content with encoding detection",
            },
            "lines": {
                "type": "bool",
                "default": False,
                "description": (
                    "Include file content split into lines array. "
                    "Fails if used with binary files or hex/base64 encoding. "
                    "Implies content reading is enabled"
                ),
            },
            "encoding": {
                "type": "str",
                "default": None,
                "description": (
                    "Force specific encoding instead of auto-detection. "
                    "Supports standard encodings (utf-8, iso-8859-1, "
                    "shift-jis, etc.), 'base64' for binary data, and 'hex' "
                    "for hexadecimal representation. Fails if decode fails. "
                    "Only used when content=true or lines=true"
                ),
            },
            "mime": {
                "type": "bool",
                "default": False,
                "description": "Detect MIME type using file command",
            },
            "md5": {
                "type": "bool",
                "default": False,
                "description": "Calculate MD5 checksum of file content",
            },
            "sha1": {
                "type": "bool",
                "default": False,
                "description": "Calculate SHA-1 checksum of file content",
            },
            "sha256": {
                "type": "bool",
                "default": False,
                "description": "Calculate SHA-256 checksum of file content",
            },
            "sha512": {
                "type": "bool",
                "default": False,
                "description": "Calculate SHA-512 checksum of file content",
            },
            "parents": {
                "type": "raw",
                "default": False,
                "description": (
                    "Recursively read parent directories (using dirname) "
                    "and include their metadata. Can be a boolean (True "
                    "for unlimited recursion up to root) or a positive "
                    "integer (maximum directory levels to ascend)"
                ),
            },
            "follow": {
                "type": "raw",
                "default": True,
                "description": (
                    "How to handle symbolic links. Can be a boolean or "
                    "the string 'recursive'. True (default) resolves to the "
                    "ultimate target (like readlink -f). 'recursive' adds "
                    "link targets to the paths list recursively until a "
                    "non-symlink is found. False lists the link without "
                    "following or recursing"
                ),
            },
            "children": {
                "type": "raw",
                "default": False,
                "description": (
                    "Recursively read child entries within directories. "
                    "Can be a boolean (True for unlimited recursion into "
                    "all subdirectories) or a positive integer (maximum "
                    "directory depth to descend). Has no effect on "
                    "non-directory entries"
                ),
            },
        }

        # Check if user explicitly provided metadata before validation
        metadata_explicitly_set = "metadata" in self._task.args

        validation_result, new_module_args = self.validate_argument_spec(
            argument_spec=argument_spec
        )

        # Set instance variables from validated args
        self.paths = new_module_args["paths"]
        self.metadata = new_module_args["metadata"]
        self.extended = new_module_args["extended"]
        self.content = new_module_args["content"]
        self.lines = new_module_args["lines"]
        self.encoding = new_module_args["encoding"]
        self.mime = new_module_args["mime"]
        self.md5 = new_module_args["md5"]
        self.sha1 = new_module_args["sha1"]
        self.sha256 = new_module_args["sha256"]
        self.sha512 = new_module_args["sha512"]

        # Extended implies metadata
        if self.extended:
            self.metadata = True

        # Encoding implies content reading (but not lines)
        if self.encoding:
            self.content = True

        # If content/lines requested, default metadata to false
        # (unless user explicitly set it)
        if (self.content or self.lines) and not metadata_explicitly_set:
            self.metadata = False

        try:
            # Process follow parameter (boolean or 'recursive')
            self.follow = truthy_or_string(
                new_module_args["follow"], ["recursive"]
            )

            # Process parents parameter (boolean or positive integer)
            self.parents = truthy_or_integer(
                new_module_args["parents"],
                only_positive=True,
                zero_is_false=True,
            )

            # Process children parameter (boolean or positive integer)
            self.children = truthy_or_integer(
                new_module_args["children"],
                only_positive=True,
                zero_is_false=True,
            )
        except ValueError as e:
            raise AnsibleActionFail(str(e)) from e

        # Track original paths before adding parents
        # (children should only be processed for original paths,
        # not auto-added parents)
        original_paths = set(self.paths)

        # Add parent paths if requested
        if self.parents:
            parent_paths = []
            max_depth = None if self.parents is True else self.parents

            for path in self.paths:
                current_path = path
                depth = 0

                while True:
                    # Get parent directory
                    parent = dirname(current_path)

                    # Stop if we've reached root or max depth
                    if not parent or parent == current_path:
                        break
                    if max_depth is not None and depth >= max_depth:
                        break

                    parent_paths.append(parent)
                    current_path = parent
                    depth += 1

            # Merge parent paths into self.paths and deduplicate
            self.paths = list(set(self.paths + parent_paths))

        # Store original paths for children processing
        self.original_paths = original_paths

    def run(
        self,
        tmp: Optional[str] = None,
        task_vars: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """Execute file inspection and return metadata.

        :param Optional[str] tmp: Unused temporary directory path
        :param Optional[dict[str, Any]] task_vars: Available Ansible
            variables
        :returns dict[str, Any]: Result with file metadata
        """
        task_vars = task_vars or {}
        self._def_inventory_hostname(task_vars)

        self._def_args()

        result = super(ActionModule, self).run(tmp, task_vars=task_vars)
        result["invocation"] = self._task.args.copy()

        del tmp  # unused

        # Initialize counters for tracking total commands and batches
        total_commands = 0
        total_batches = 0

        # Platform detection: check for cached facts first
        # (always None for now)
        # TODO: In the future, check task_vars for cached platform
        # facts from o0_os['platform'] before falling back to runtime
        # detection.
        platform: Optional[dict[str, Any]] = None

        # Build options dict from parameters
        options = {
            "metadata": self.metadata,
            "extended": self.extended,
            "content": self.content,
            "lines": self.lines,
            "encoding": self.encoding,
            "mime": self.mime,
            "md5": self.md5,
            "sha1": self.sha1,
            "sha256": self.sha256,
            "sha512": self.sha512,
        }

        # Two-phase approach: detect platform from first path, then use
        # detected capabilities for remaining paths to avoid redundant commands
        file_data: dict[str, Any] = {}

        if self.paths:
            # Phase 1: Process first path with all command variants (detection)
            first_path = self.paths[0]
            detection_commands = self._get_read_commands(
                [first_path],
                options,
                need_dir_contents=bool(self.children),
                platform=None,  # Detection mode: run all variants
            )
            self._display.vvv(
                f"[{self.inventory_hostname}] Platform detection: generated "
                f"{len(detection_commands)} commands for {first_path}"
            )

            detection_result = self._run(
                commands=detection_commands,
                task_vars=task_vars,
                check_mode=False,
            )
            total_commands += detection_result.get("count", 0)
            total_batches += detection_result.get("batches", 0)
            self._display_longest_command(
                detection_result, "platform detection"
            )

            # Detect platform capabilities from first path's results
            platform = self._detect_platform_from_results(
                detection_result["commands"], first_path
            )
            self._display.vvv(
                f"[{self.inventory_hostname}] Detected platform: "
                f"stat={platform['stat_variant']}, "
                f"lsattr={platform['has_lsattr']}, "
                f"getfacl={platform['has_getfacl']}, "
                f"flags_bsd={platform['ls_supports_flags_bsd']}"
            )

            # Process first path's results
            first_file_data = self._process_read_results(
                results=detection_result["commands"],
                paths=[first_path],
                options=options,
            )
            file_data.update(first_file_data)

            # Phase 2: Process remaining paths with detected platform
            remaining_paths = self.paths[1:]
            if remaining_paths:
                commands = self._get_read_commands(
                    remaining_paths,
                    options,
                    need_dir_contents=bool(self.children),
                    platform=platform,
                )
                self._display.vvv(
                    f"[{self.inventory_hostname}] Generated {len(commands)} "
                    f"commands for {len(remaining_paths)} remaining paths"
                )

                commands_result = self._run(
                    commands=commands,
                    task_vars=task_vars,
                    check_mode=False,
                )
                total_commands += commands_result.get("count", 0)
                total_batches += commands_result.get("batches", 0)
                self._display_longest_command(
                    commands_result, "remaining paths"
                )

                # Process remaining results
                remaining_file_data = self._process_read_results(
                    results=commands_result["commands"],
                    paths=remaining_paths,
                    options=options,
                )
                file_data.update(remaining_file_data)

        # If children is set, recursively read child entries within directories
        if self.children:
            max_depth = None if self.children is True else self.children
            self._display.vvv(
                f"[{self.inventory_hostname}] Children processing enabled "
                f"(max_depth={max_depth})"
            )

            # Track directories to process with their depth
            # Start with original paths that are directories
            # (don't process children for auto-added parent paths)
            dirs_to_process = []
            for path in self.original_paths:
                if (
                    path in file_data
                    and file_data[path]
                    and file_data[path].get("type") == "directory"
                ):
                    dirs_to_process.append((path, 0))

            self._display.vvv(
                f"[{self.inventory_hostname}] Found {len(dirs_to_process)} "
                f"initial directories to process"
            )

            processed_dirs = set()

            while dirs_to_process:
                current_dir, current_depth = dirs_to_process.pop(0)

                # Skip if already processed or exceeded depth
                if current_dir in processed_dirs:
                    continue
                if max_depth is not None and current_depth >= max_depth:
                    continue

                processed_dirs.add(current_dir)

                # Get children from this directory
                dir_data = file_data.get(current_dir)
                if not dir_data or "children" not in dir_data:
                    self._display.vvv(
                        f"[{self.inventory_hostname}] Skipping {current_dir} "
                        f"(no children)"
                    )
                    continue

                child_paths = dir_data["children"]
                if not child_paths:
                    self._display.vvv(
                        f"[{self.inventory_hostname}] Directory {current_dir} "
                        f"is empty"
                    )
                    continue

                self._display.vvv(
                    f"[{self.inventory_hostname}] Processing {current_dir} "
                    f"(depth={current_depth}, {len(child_paths)} children)"
                )

                # Filter out children that are already in file_data
                new_children = [
                    child for child in child_paths if child not in file_data
                ]

                self._display.vvv(
                    f"[{self.inventory_hostname}] Found {len(new_children)} "
                    f"new children to read"
                )

                if new_children:
                    # Process children in batches to avoid SSH buffer overflow
                    batch_size = 50
                    for batch_start in range(0, len(new_children), batch_size):
                        batch_end = min(
                            batch_start + batch_size, len(new_children)
                        )
                        batch_paths = new_children[batch_start:batch_end]

                        self._display.vvv(
                            f"[{self.inventory_hostname}] Processing batch "
                            f"{batch_start // batch_size + 1} "
                            f"({len(batch_paths)} paths)"
                        )

                        # Read metadata for this batch of children
                        child_commands = self._get_read_commands(
                            batch_paths,
                            options,
                            need_dir_contents=True,
                            platform=platform,
                        )
                        self._display.vvv(
                            f"[{self.inventory_hostname}] Generated "
                            f"{len(child_commands)} commands for "
                            f"{len(batch_paths)} paths"
                        )
                        child_result = self._run(
                            commands=child_commands,
                            task_vars=task_vars,
                            check_mode=False,
                        )
                        total_commands += child_result.get("count", 0)
                        total_batches += child_result.get("batches", 0)
                        self._display_longest_command(
                            child_result,
                            f"children batch {batch_start // batch_size + 1}",
                        )
                        child_data = self._process_read_results(
                            results=child_result["commands"],
                            paths=batch_paths,
                            options=options,
                        )
                        file_data.update(child_data)

                # Add subdirectories to processing queue (outside batch loop)
                subdirs_found = 0
                for child_path in new_children:
                    if (
                        child_path in file_data
                        and file_data[child_path]
                        and file_data[child_path].get("type") == "directory"
                    ):
                        dirs_to_process.append((child_path, current_depth + 1))
                        subdirs_found += 1

                if subdirs_found > 0:
                    self._display.vvv(
                        f"[{self.inventory_hostname}] Added "
                        f"{subdirs_found} subdirectories to queue "
                        f"(queue size now: {len(dirs_to_process)})"
                    )

        # Handle symbolic links based on follow parameter
        if self.follow == "recursive":
            # Recursively add symlink targets until non-symlink found
            processed_paths = set(file_data.keys())

            while True:
                new_targets = []
                for path, data in file_data.items():
                    if (
                        data
                        and data.get("type") == "link"
                        and "target" in data
                        and data["target"]
                    ):
                        target = data["target"]
                        # Resolve relative paths to absolute
                        if not isabs(target):
                            target = normpath(join(dirname(path), target))
                        if target not in processed_paths:
                            new_targets.append(target)
                            processed_paths.add(target)

                if not new_targets:
                    break

                # Read metadata for link targets
                target_commands = self._get_read_commands(
                    new_targets, options, platform=platform
                )
                target_result = self._run(
                    commands=target_commands,
                    task_vars=task_vars,
                    check_mode=False,
                )
                total_commands += target_result.get("count", 0)
                total_batches += target_result.get("batches", 0)
                self._display_longest_command(
                    target_result, "recursive symlink targets"
                )
                target_data = self._process_read_results(
                    results=target_result["commands"],
                    paths=new_targets,
                    options=options,
                )
                file_data.update(target_data)

        elif self.follow is True:
            # Resolve symlinks to their ultimate targets
            links_to_resolve = []
            for path, data in file_data.items():
                if data and data.get("type") == "link":
                    links_to_resolve.append(path)

            if links_to_resolve:
                # Use readlink -f to resolve ultimate targets
                readlink_commands = {}
                for link_path in links_to_resolve:
                    readlink_commands[f"{link_path}_readlink"] = [
                        "readlink",
                        "-f",
                        link_path,
                    ]

                readlink_result = self._run(
                    commands=readlink_commands,
                    task_vars=task_vars,
                    check_mode=False,
                )
                total_commands += readlink_result.get("count", 0)
                total_batches += readlink_result.get("batches", 0)
                self._display_longest_command(readlink_result, "readlink -f")

                # Get resolved targets and read their metadata
                resolved_targets = {}
                for link_path in links_to_resolve:
                    result_key = f"{link_path}_readlink"
                    if result_key in readlink_result["commands"]:
                        cmd_result = readlink_result["commands"][result_key]
                        if cmd_result.get("rc") == 0:
                            target = cmd_result.get("stdout", "").strip()
                            if target:
                                resolved_targets[link_path] = target

                # Read metadata for resolved targets
                if resolved_targets:
                    unique_targets = list(set(resolved_targets.values()))
                    target_commands = self._get_read_commands(
                        unique_targets, options, platform=platform
                    )
                    target_result = self._run(
                        commands=target_commands,
                        task_vars=task_vars,
                        check_mode=False,
                    )
                    total_commands += target_result.get("count", 0)
                    total_batches += target_result.get("batches", 0)
                    self._display_longest_command(
                        target_result, "resolved symlink targets"
                    )
                    target_data = self._process_read_results(
                        results=target_result["commands"],
                        paths=unique_targets,
                        options=options,
                    )

                    # Replace symlink data with target data
                    for link_path, target in resolved_targets.items():
                        if target in target_data and target_data[target]:
                            file_data[link_path] = target_data[target]
                            # Add realpath key when it differs from
                            # original path
                            if target != link_path:
                                file_data[link_path]["realpath"] = target

        # Note: children field is always kept in output since it's controlled
        # by the children parameter (not the old include list)

        # Format output
        result["changed"] = False
        result["paths"] = file_data
        result["commands"] = total_commands
        result["batches"] = total_batches

        return result
