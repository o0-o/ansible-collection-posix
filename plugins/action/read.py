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
            "include": {
                "type": "list",
                "elements": "str",
                "default": ["metadata"],
                "description": (
                    "Fields to include in the result. "
                    "'all' includes everything (metadata + extended + content + children). "
                    "'metadata' includes basic metadata and extended filesystem attributes: "
                    "type, mode, owner, group, size, writable, hardlinks, inode, "
                    "timestamps (modified, created, changed), ACL, filesystem flags, "
                    "and SELinux context (but NOT xattrs). "
                    "'extended' includes all metadata plus extended attributes (xattrs). "
                    "'content' includes file content with encoding detection. "
                    "'children' includes directory child paths."
                ),
                "choices": [
                    "all",
                    "metadata",
                    "extended",
                    "content",
                    "children",
                ],
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
                    "the string 'recurse'. True (default) resolves to the "
                    "ultimate target (like readlink -f). 'recurse' adds "
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

        validation_result, new_module_args = self.validate_argument_spec(
            argument_spec=argument_spec
        )

        # Set instance variables from validated args
        self.paths = new_module_args["paths"]
        self.include = new_module_args["include"]

        try:
            # Process follow parameter (boolean or 'recurse')
            self.follow = truthy_or_string(
                new_module_args["follow"], ["recurse"]
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
        # (children should only be processed for original paths, not auto-added parents)
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

        # Generate batched commands for all paths
        # Pass need_dir_contents=True when children is enabled to get directory listings
        commands = self._get_read_commands(
            self.paths, self.include, need_dir_contents=bool(self.children)
        )
        self._display.vvv(
            f"[{self.inventory_hostname}] Generated {len(commands)} "
            f"commands for {len(self.paths)} initial paths"
        )

        # Execute all commands in single batch
        commands_result = self._run(
            commands=commands,
            task_vars=task_vars,
            check_mode=False,
        )

        # Process all results
        file_data = self._process_read_results(
            results=commands_result["commands"],
            paths=self.paths,
            include=self.include,
        )

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
                            self.include,
                            need_dir_contents=True,
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
                        child_data = self._process_read_results(
                            results=child_result["commands"],
                            paths=batch_paths,
                            include=self.include,
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
        if self.follow == "recurse":
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
                    new_targets, self.include
                )
                target_result = self._run(
                    commands=target_commands,
                    task_vars=task_vars,
                    check_mode=False,
                )
                target_data = self._process_read_results(
                    results=target_result["commands"],
                    paths=new_targets,
                    include=self.include,
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
                        unique_targets, self.include
                    )
                    target_result = self._run(
                        commands=target_commands,
                        task_vars=task_vars,
                        check_mode=False,
                    )
                    target_data = self._process_read_results(
                        results=target_result["commands"],
                        paths=unique_targets,
                        include=self.include,
                    )

                    # Replace symlink data with target data
                    for link_path, target in resolved_targets.items():
                        if target in target_data and target_data[target]:
                            file_data[link_path] = target_data[target]
                            # Add realpath key when it differs from original path
                            if target != link_path:
                                file_data[link_path]["realpath"] = target

        # Remove children field from output if not explicitly requested
        # (it was needed internally for children parameter processing)
        if "all" not in self.include and "children" not in self.include:
            for path_data in file_data.values():
                if path_data and "children" in path_data:
                    del path_data["children"]

        # Format output
        result["changed"] = False
        result["paths"] = file_data

        return result
