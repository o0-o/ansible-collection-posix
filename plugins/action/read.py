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

import base64
import os
import posixpath
import shlex
from typing import Any, Dict, List, Optional, Tuple

from ansible.errors import AnsibleActionFail
from ansible.plugins.action import ActionBase

from ansible_collections.o0_o.posix.plugins.module_utils import PosixActionBase
from ansible_collections.o0_o.utils.plugins.module_utils import (
    truthy_or_integer,
)


class ActionModule(PosixActionBase, ActionBase):
    """Inspect file metadata and optionally return printable content.

    Gathers comprehensive metadata about files, directories, links, and
    special devices on POSIX systems. Supports content retrieval with
    encoding detection and recursive link traversal.
    """

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
        """Execute file inspection and return metadata.

        :param Optional[str] tmp: Unused temporary directory path
        :param Optional[Dict[str, Any]] task_vars: Available Ansible
            variables
        :returns Dict[str, Any]: Result with file metadata under 'file'
            key
        :raises AnsibleActionFail: When invalid arguments are provided
        """
        task_vars = task_vars or {}
        tmp = None

        result = super().run(tmp, task_vars)

        argument_spec = {
            "paths": {
                "type": "list",
                "required": True,
                "elements": "str",
                "aliases": ["path"],
            },
            "content": {"type": "bool", "default": False},
            "encoding": {"type": "str"},
            "parents": {"type": "raw", "default": False},
            "find_hardlinks": {"type": "bool", "default": False},
            "find_symlinks": {"type": "bool", "default": False},
        }
        validation_result, new_args = self.validate_argument_spec(
            argument_spec=argument_spec
        )

        path_list = new_args["paths"]

        include_content = new_args["content"]
        preferred_encoding = new_args.get("encoding")
        parents_option = truthy_or_integer(
            new_args["parents"], zero_is_false=True, only_positive=True
        )
        parents = False
        parent_limit: Optional[int] = 0
        if parents_option is True:
            parents = True
            parent_limit = None
        elif parents_option is False:
            parent_limit = 0
        else:
            parents = True
            parent_limit = parents_option
        find_hardlinks = new_args.get("find_hardlinks", False)
        find_symlinks = new_args.get("find_symlinks", False)

        files: Dict[str, Optional[Dict[str, Any]]] = {}
        for current_path in path_list:
            visited_paths: set[str] = set()

            info, extra_entries = self._gather_file_info(
                path=current_path,
                include_content=include_content,
                preferred_encoding=preferred_encoding,
                task_vars=task_vars,
                parents=parents,
                find_hardlinks=find_hardlinks,
                find_symlinks=find_symlinks,
                visited=visited_paths,
            )
            files[current_path] = info
            for extra_path, extra_info in extra_entries.items():
                if extra_path in files:
                    continue
                files[extra_path] = extra_info

        if parent_limit is None:
            parent_paths_iter = self._collect_parent_paths(current_path, None)
        elif parent_limit > 0:
            parent_paths_iter = self._collect_parent_paths(
                current_path, parent_limit
            )
        else:
            parent_paths_iter = []

        for parent_path in parent_paths_iter:
            if parent_path in files:
                continue
            parent_info, parent_extra = self._gather_file_info(
                path=parent_path,
                include_content=False,
                preferred_encoding=None,
                task_vars=task_vars,
                parents=False,
                find_hardlinks=False,
                find_symlinks=False,
                visited=visited_paths,
            )
            if parent_info is not None:
                files[parent_path] = parent_info
            for extra_path, extra_info in parent_extra.items():
                if extra_path not in files:
                    files[extra_path] = extra_info

        result.update(
            {
                "changed": False,
                "paths": files,
            }
        )
        return result

    def _gather_file_info(
        self,
        path: str,
        include_content: bool,
        preferred_encoding: Optional[str],
        task_vars: Optional[Dict[str, Any]],
        parents: bool,
        find_hardlinks: bool,
        find_symlinks: bool,
        visited: Optional[set[str]] = None,
    ) -> Tuple[Optional[Dict[str, Any]], Dict[str, Optional[Dict[str, Any]]]]:
        """Gather comprehensive metadata about a file system path.

        :param str path: Path to inspect
        :param bool include_content: Whether to read file content
        :param Optional[str] preferred_encoding: Override encoding
            detection
        :param Optional[Dict[str, Any]] task_vars: Available Ansible
            variables
        :param bool parents: Whether to expand related paths discovered
            while gathering metadata
        :param bool find_hardlinks: Perform a full filesystem scan to
            enumerate hard link paths. This is extremely expensive on
            anything but very small mounts such as /dev.
        :param bool find_symlinks: Perform a full filesystem scan to
            discover symbolic links targeting the inspected path.
        :param Optional[set[str]] visited: Paths already visited to
            prevent cycles
        :returns Tuple[Optional[Dict[str, Any]], Dict[str, Optional[Dict[str, Any]]]]:
            File metadata (or None when missing) and additional entries
            to report in the top-level mapping.
        """
        visited = set(visited or set())
        if path in visited:
            return None, {}
        visited.add(path)

        stat_result = self._run_action(
            "ansible.builtin.stat",
            {
                "path": path,
                "follow": False,
                "get_attributes": True,
                "get_checksum": False,
                "get_mime": False,
            },
            task_vars=task_vars,
        )
        stat_data = stat_result.get("stat", {})
        if not stat_data.get("exists"):
            return None, {}

        info: Dict[str, Any] = {}
        extra_paths: Dict[str, Optional[Dict[str, Any]]] = {}

        normalized_path = posixpath.normpath(path)

        file_type = self._determine_type(stat_data)
        if file_type:
            info["type"] = file_type

        if normalized_path == posixpath.sep:
            info["name"] = posixpath.sep
        else:
            info["name"] = (
                posixpath.basename(normalized_path) or normalized_path
            )
            parent_dir = posixpath.dirname(normalized_path) or posixpath.sep
            info["parent"] = parent_dir

        mode = stat_data.get("mode")
        if mode:
            info["mode"] = mode

        owner = stat_data.get("pw_name") or stat_data.get("uid")
        if owner is not None:
            info["owner"] = owner
        group = stat_data.get("gr_name") or stat_data.get("gid")
        if group is not None:
            info["group"] = group

        writeable = stat_data.get("writeable")
        if writeable is None:
            writeable = stat_data.get("writable")
        if writeable is not None:
            info["writable"] = bool(writeable)

        link_paths: List[str] = []

        link_target = stat_data.get("lnk_source")
        display_link = None
        if link_target:
            display_link = self._resolve_symbolic_target(
                path=path,
                link_target=link_target,
                task_vars=task_vars,
            )
        if display_link:
            nested_info, nested_extra = self._gather_file_info(
                path=link_target,
                include_content=include_content,
                preferred_encoding=preferred_encoding,
                task_vars=task_vars,
                parents=parents,
                find_hardlinks=find_hardlinks,
                find_symlinks=find_symlinks,
                visited=visited,
            )
            extra_paths.update(nested_extra)
            if display_link not in extra_paths:
                extra_paths[display_link] = nested_info
            link_paths.append(display_link)

        nlink_raw = stat_data.get("nlink")
        try:
            nlink_value = int(nlink_raw) if nlink_raw is not None else None
        except (TypeError, ValueError):
            nlink_value = None

        other_link_count = 0
        if nlink_value is not None and nlink_value > 0:
            other_link_count = max(nlink_value - 1, 0)

        inode_value = self._extract_inode(stat_data)

        reference_inodes: set[int] = set()
        if inode_value is not None:
            reference_inodes.add(inode_value)

        target_inode_value = None
        if find_symlinks:
            follow_stat = self._stat_follow(path, task_vars)
            follow_stat_data = (
                follow_stat.get("stat", {}) if follow_stat else {}
            )
            target_inode_value = self._extract_inode(follow_stat_data)
            if target_inode_value is not None:
                reference_inodes.add(target_inode_value)

        hard_links: List[str] = []
        symlink_candidates: List[str] = []
        if find_hardlinks or find_symlinks:
            hard_links, symlink_candidates = self._discover_links(
                path=path,
                task_vars=task_vars,
                inode=inode_value,
                file_type=file_type,
                expected_total=nlink_value,
                include_hardlinks=find_hardlinks,
                include_symlinks=find_symlinks,
            )

        if hard_links and find_hardlinks:
            for hard_path in hard_links:
                display_hard = posixpath.normpath(hard_path)
                if parents:
                    if hard_path in visited:
                        continue
                    hard_info, nested_extra = self._gather_file_info(
                        path=hard_path,
                        include_content=include_content,
                        preferred_encoding=preferred_encoding,
                        task_vars=task_vars,
                        parents=True,
                        find_hardlinks=find_hardlinks,
                        find_symlinks=find_symlinks,
                        visited=visited,
                    )
                    extra_paths.update(nested_extra)
                    if display_hard not in extra_paths:
                        extra_paths[display_hard] = hard_info
                link_paths.append(display_hard)

            if find_symlinks:
                for hard_path in hard_links:
                    extra_paths.update(
                        self._collect_symlink_refs(
                            target=hard_path,
                            include_content=include_content,
                            preferred_encoding=preferred_encoding,
                            task_vars=task_vars,
                            parents=parents,
                            visited=visited,
                        )
                    )

        if link_paths:
            unique_links: List[str] = []
            for candidate in link_paths:
                if candidate not in unique_links:
                    unique_links.append(candidate)
            info["links"] = unique_links
        elif other_link_count > 0:
            info["links"] = other_link_count

        if find_symlinks and symlink_candidates:
            valid_symlinks = self._filter_symlinks(
                candidates=symlink_candidates,
                task_vars=task_vars,
                reference_inodes=reference_inodes,
                current_path=path,
            )
            for symlink_path in valid_symlinks:
                if symlink_path in visited:
                    continue
                symlink_info, nested_extra = self._gather_file_info(
                    path=symlink_path,
                    include_content=include_content,
                    preferred_encoding=preferred_encoding,
                    task_vars=task_vars,
                    parents=parents,
                    find_hardlinks=False,
                    find_symlinks=False,
                    visited=visited,
                )
                extra_paths.update(nested_extra)
                extra_paths[symlink_path] = symlink_info

        if find_symlinks and link_target and not parents and find_hardlinks:
            extra_paths.update(
                self._collect_symlink_refs(
                    target=link_target,
                    include_content=include_content,
                    preferred_encoding=preferred_encoding,
                    task_vars=task_vars,
                    parents=parents,
                    visited=visited,
                )
            )

        selinux = stat_data.get("selinux_label")
        if selinux:
            info["selinux"] = selinux

        attr_flags = stat_data.get("attr_flags")
        if attr_flags:
            info["flags"] = self._normalize_flags(attr_flags)

        xattrs = stat_data.get("xattrs")
        names, acl_entries, selinux_extra = self._process_xattrs(xattrs)
        if names:
            info["xattrs"] = names
        for acl_entry in acl_entries:
            self._merge_acl(info, acl_entry)
        if selinux_extra and "selinux" not in info:
            info["selinux"] = selinux_extra

        if file_type == "directory" and include_content:
            directory_entries = self._list_directory(path, task_vars)
            if directory_entries is not None:
                info["content"] = directory_entries

        skip_extended_metadata = file_type == "pipe"

        if not skip_extended_metadata:
            acl_data = self._get_acl(path, task_vars)
            if acl_data:
                self._merge_acl(info, acl_data)

            if "flags" not in info:
                flags = self._get_flags(path, task_vars)
                if flags:
                    info["flags"] = self._normalize_flags(flags)

            if "xattrs" not in info:
                xattr_fallback = self._get_xattrs(path, task_vars)
                names_fb, acl_entries_fb, selinux_fb = self._process_xattrs(
                    xattr_fallback
                )
                if names_fb:
                    info["xattrs"] = names_fb
                for acl_entry in acl_entries_fb:
                    self._merge_acl(info, acl_entry)
                if selinux_fb and "selinux" not in info:
                    info["selinux"] = selinux_fb

        encoding, content_text = self._maybe_get_content(
            path=path,
            include_content=include_content,
            preferred_encoding=preferred_encoding,
            stat_data=stat_data,
            task_vars=task_vars,
        )
        if encoding:
            info["encoding"] = encoding
        if content_text is not None:
            info["content"] = content_text

        return info, extra_paths

    def _list_directory(
        self, path: str, task_vars: Optional[Dict[str, Any]]
    ) -> Optional[List[str]]:
        """List direct children of a directory path."""

        command = [
            "find",
            path,
            "-mindepth",
            "1",
            "-maxdepth",
            "1",
            "-print",
        ]
        result = self._cmd(command, task_vars=task_vars, check_mode=False)
        if result.get("rc") != 0:
            return None
        entries: List[str] = []
        for line in (result.get("stdout") or "").splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            entries.append(posixpath.normpath(stripped))

        if not entries:
            return []
        return sorted(set(entries))

    def _determine_type(self, stat_data: Dict[str, Any]) -> Optional[str]:
        """Determine file type from stat data.

        :param Dict[str, Any] stat_data: Stat module output
        :returns Optional[str]: File type label or None
        """
        mapping = {
            "isreg": "regular",
            "isdir": "directory",
            "islnk": "link",
            "isfifo": "pipe",
            "issock": "socket",
            "ischr": "character",
            "isblk": "block",
        }
        for key, label in mapping.items():
            if stat_data.get(key):
                return label
        return None

    def _resolve_symbolic_target(
        self,
        path: str,
        link_target: str,
        task_vars: Optional[Dict[str, Any]],
    ) -> Optional[str]:
        """Determine the best display value for a symlink target.

        Prefers the literal symlink payload obtained via C(readlink)
        when available so callers receive the same path string the
        filesystem stores, falling back to the stat-provided value.

        :param str path: Symlink path to inspect
        :param str link_target: Target reported by the stat module
        :param Optional[Dict[str, Any]] task_vars: Available Ansible
            variables
        :returns Optional[str]: Normalized target string or None when
            unavailable
        """
        candidates: List[str] = []

        readlink_result = self._cmd(
            ["readlink", path],
            task_vars=task_vars,
            check_mode=False,
        )
        if readlink_result.get("rc") == 0:
            output = (readlink_result.get("stdout") or "").strip()
            if output:
                if posixpath.isabs(output):
                    candidates.append(output)
                else:
                    base_dir = posixpath.dirname(path) or "."
                    combined = posixpath.join(base_dir, output)
                    candidates.append(combined)

        if link_target:
            candidates.append(link_target)

        for candidate in candidates:
            if not candidate:
                continue
            normalized = posixpath.normpath(candidate)
            if normalized:
                return normalized
        return None

    def _extract_inode(self, stat_data: Dict[str, Any]) -> Optional[int]:
        """Extract inode number from stat output when present."""

        for key in ("inode", "ino"):
            candidate = stat_data.get(key)
            if candidate is None:
                continue
            try:
                return int(candidate)
            except (TypeError, ValueError):
                continue
        return None

    def _stat_follow(
        self,
        path: str,
        task_vars: Optional[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        """Retrieve stat data with symlink following enabled."""

        try:
            return self._run_action(
                "ansible.builtin.stat",
                {
                    "path": path,
                    "follow": True,
                    "get_attributes": True,
                    "get_checksum": False,
                    "get_mime": False,
                },
                task_vars=task_vars,
            )
        except AnsibleActionFail:
            return None

    def _get_mount_root(
        self,
        path: str,
        task_vars: Optional[Dict[str, Any]],
    ) -> Optional[str]:
        """Determine the mount point that contains the path.

        :param str path: Path to evaluate
        :param Optional[Dict[str, Any]] task_vars: Available Ansible
            variables
        :returns Optional[str]: Mount point directory or None when
            detection fails
        """
        df_result = self._cmd(
            ["df", "-P", path],
            task_vars=task_vars,
            check_mode=False,
        )
        if df_result.get("rc") != 0:
            return None
        stdout = (df_result.get("stdout") or "").strip()
        lines = [line for line in stdout.splitlines() if line.strip()]
        if len(lines) < 2:
            return None
        fields = lines[-1].split()
        if len(fields) < 6:
            return None
        mount_point = fields[-1]
        if not mount_point:
            return None
        return mount_point

    def _discover_links(
        self,
        path: str,
        task_vars: Optional[Dict[str, Any]],
        inode: Optional[int],
        file_type: Optional[str],
        expected_total: Optional[int],
        include_hardlinks: bool,
        include_symlinks: bool,
    ) -> Tuple[List[str], List[str]]:
        """Discover hard link and symlink references for a path."""

        if not include_hardlinks and not include_symlinks:
            return [], []

        if (
            include_hardlinks
            and expected_total is not None
            and expected_total <= 1
        ):
            include_hardlinks = False

        if include_hardlinks and inode is None:
            probe = self._cmd(
                ["ls", "-li", "--", path],
                task_vars=task_vars,
                check_mode=False,
            )
            if probe.get("rc") == 0:
                stdout = (probe.get("stdout") or "").strip()
                if stdout:
                    first_line = stdout.splitlines()[0]
                    fragments = first_line.strip().split()
                    if fragments:
                        try:
                            inode = int(fragments[0])
                        except (TypeError, ValueError):
                            inode = None
        if include_hardlinks and inode is None:
            include_hardlinks = False

        mount_root = self._get_mount_root(path, task_vars)
        search_root = mount_root or posixpath.dirname(path) or "/"

        if include_hardlinks and not include_symlinks:
            legacy = self._find_hard_links(
                path=path,
                task_vars=task_vars,
                inode=inode,
                file_type=file_type,
                expected_total=expected_total,
            )
            return legacy or [], []

        type_map = {
            "regular": "f",
            "directory": "d",
            "link": "l",
            "pipe": "p",
            "socket": "s",
            "character": "c",
            "block": "b",
        }
        type_flag = type_map.get(file_type or "")

        normalized_path = posixpath.normpath(path)
        path_dir = posixpath.dirname(path) or "."

        max_links = None
        if include_hardlinks and expected_total is not None:
            max_links = max(expected_total - 1, 0)

        def append_unique(target: List[str], value: str) -> None:
            if value not in target:
                target.append(value)

        def is_same_path(first: str, second: str) -> bool:
            try:
                return os.path.samefile(first, second)
            except OSError:
                return False

        def build_command(
            root: str,
            limit: Optional[int],
            restrict_dev: bool,
            max_depth: Optional[int],
        ) -> List[str]:
            find_parts: List[str] = ["find", shlex.quote(root)]
            if restrict_dev:
                find_parts.append("-xdev")
            if max_depth is not None:
                find_parts.extend(["-maxdepth", str(max_depth)])

            expressions: List[str] = []
            if include_hardlinks:
                hard_chunks = [r"\(", f"-samefile {shlex.quote(path)}"]
                if type_flag:
                    hard_chunks.append(f"-type {shlex.quote(type_flag)}")
                hard_chunks.extend(
                    [
                        "-exec",
                        "sh",
                        "-c",
                        '\'printf "H:%s\\n" "$1"\'',
                        "sh",
                        "{}",
                        r"\;",
                        r"\)",
                    ]
                )
                expressions.append(" ".join(hard_chunks))
            if include_symlinks:
                sym_chunks = [
                    r"\(",
                    "-type",
                    "l",
                    "-exec",
                    "sh",
                    "-c",
                    '\'printf "S:%s\\n" "$1"\'',
                    "sh",
                    "{}",
                    r"\;",
                    r"\)",
                ]
                expressions.append(" ".join(sym_chunks))

            if expressions:
                if len(expressions) == 1:
                    find_parts.append(expressions[0])
                else:
                    find_parts.append(
                        r"\( " + " -o ".join(expressions) + r" \)"
                    )

            find_str = " ".join(find_parts)
            if include_hardlinks:
                if include_symlinks:
                    pipeline = find_str
                elif limit is not None and limit > 0:
                    pipeline = f"{find_str} | head -n {limit}"
                else:
                    pipeline = find_str
            else:
                pipeline = find_str
            return ["sh", "-c", pipeline, "sh"]

        hard_results: List[str] = []
        symlink_results: List[str] = []

        search_plans = [
            (path_dir, expected_total, True, None, "path_dir_head"),
            (path_dir, None, True, None, "path_dir_full"),
            (search_root, expected_total, True, None, "mount_head"),
            (search_root, None, True, None, "mount_full"),
            (path_dir, None, False, 1, "path_dir_one_level"),
            (path_dir, expected_total, False, 1, "path_dir_one_level_head"),
            (search_root, None, False, None, "mount_crossdev"),
        ]

        for root, limit, restrict_dev, max_depth, label in search_plans:
            if (
                include_hardlinks
                and max_links is not None
                and len(hard_results) >= max_links
            ):
                break

            command = build_command(
                root=root,
                limit=limit,
                restrict_dev=restrict_dev,
                max_depth=max_depth,
            )
            self._display.vvv(
                f"[read] link scan {label} command={' '.join(command)}"
            )
            result = self._cmd(
                command,
                task_vars=task_vars,
                check_mode=False,
            )
            if result.get("rc") != 0:
                self._display.vvv(
                    f"[read] link scan {label} failed rc={result.get('rc')}"
                )
                continue

            lines = [
                line.strip()
                for line in (result.get("stdout") or "").splitlines()
                if line.strip()
            ]
            if not lines:
                continue

            for entry in lines:
                if include_symlinks and entry.startswith("S:"):
                    candidate = posixpath.normpath(entry[2:])
                    if candidate == normalized_path:
                        continue
                    append_unique(symlink_results, candidate)
                    continue

                if include_hardlinks:
                    candidate = entry[2:] if entry.startswith("H:") else entry
                    normalized_candidate = posixpath.normpath(candidate)
                    if normalized_candidate == normalized_path:
                        continue
                    candidate_dir = posixpath.dirname(candidate) or "."
                    display_candidate = candidate
                    if is_same_path(candidate_dir, path_dir):
                        display_candidate = posixpath.normpath(
                            posixpath.join(
                                path_dir, posixpath.basename(candidate)
                            )
                        )
                    display_normalized = posixpath.normpath(display_candidate)
                    if display_normalized == normalized_path:
                        continue
                    append_unique(hard_results, display_normalized)
                    if (
                        max_links is not None
                        and len(hard_results) >= max_links
                    ):
                        break

            if (
                include_hardlinks
                and max_links is not None
                and len(hard_results) >= max_links
            ):
                break

        return hard_results, symlink_results

    def _find_hard_links(
        self,
        path: str,
        task_vars: Optional[Dict[str, Any]],
        inode: Optional[int],
        file_type: Optional[str],
        expected_total: Optional[int],
    ) -> Optional[List[str]]:
        """Legacy hard link discovery using targeted find scans."""

        if expected_total is not None and expected_total <= 1:
            return None

        if inode is None:
            probe = self._cmd(
                ["ls", "-li", "--", path],
                task_vars=task_vars,
                check_mode=False,
            )
            if probe.get("rc") == 0:
                stdout = (probe.get("stdout") or "").strip()
                if stdout:
                    first_line = stdout.splitlines()[0]
                    fragments = first_line.strip().split()
                    if fragments:
                        try:
                            inode = int(fragments[0])
                        except (TypeError, ValueError):
                            inode = None
        if inode is None:
            return None

        mount_root = self._get_mount_root(path, task_vars)
        search_root = mount_root or posixpath.dirname(path) or "/"

        type_map = {
            "regular": "f",
            "directory": "d",
            "link": "l",
            "pipe": "p",
            "socket": "s",
            "character": "c",
            "block": "b",
        }
        type_flag = type_map.get(file_type or "")

        def build_command(
            root: str,
            limit: Optional[int],
            restrict_dev: bool = True,
            max_depth: Optional[int] = None,
        ) -> List[str]:
            find_parts: List[str] = ["find", root]
            if restrict_dev:
                find_parts.append("-xdev")
            if max_depth is not None:
                find_parts.extend(["-maxdepth", str(max_depth)])
            find_parts.extend(["-samefile", path])
            if type_flag:
                find_parts.extend(["-type", type_flag])
            find_str = " ".join(shlex.quote(part) for part in find_parts)
            if limit and limit > 0:
                pipeline = f"{find_str} | head -n {limit}"
            else:
                pipeline = find_str
            return ["sh", "-c", pipeline, "sh"]

        normalized_path = posixpath.normpath(path)
        path_dir = posixpath.dirname(path) or "."
        max_links = None
        if expected_total is not None:
            max_links = max(expected_total - 1, 0)

        def append_unique(target: List[str], value: str) -> None:
            if value not in target:
                target.append(value)

        def is_same_path(first: str, second: str) -> bool:
            try:
                return os.path.samefile(first, second)
            except OSError:
                return False

        others: List[str] = []

        def consume(
            root: str,
            limit: Optional[int],
            restrict_dev: bool,
            max_depth: Optional[int],
            label: str,
        ) -> bool:
            command = build_command(
                root,
                limit,
                restrict_dev=restrict_dev,
                max_depth=max_depth,
            )
            self._display.vvv(
                f"[read] hardlink scan {label} command={' '.join(command)}"
            )
            result = self._cmd(
                command,
                task_vars=task_vars,
                check_mode=False,
            )
            if result.get("rc") != 0:
                self._display.vvv(
                    f"[read] hardlink scan {label} failed rc={result.get('rc')}"
                )
                return False
            lines = [
                line.strip()
                for line in (result.get("stdout") or "").splitlines()
                if line.strip()
            ]
            if not lines:
                self._display.vvv(
                    f"[read] hardlink scan {label} produced no results"
                )
                return False
            for candidate in lines:
                normalized_candidate = posixpath.normpath(candidate)
                if normalized_candidate == normalized_path:
                    continue
                candidate_dir = posixpath.dirname(candidate) or "."
                display_candidate = candidate
                if is_same_path(candidate_dir, path_dir):
                    display_candidate = posixpath.normpath(
                        posixpath.join(path_dir, posixpath.basename(candidate))
                    )
                display_normalized = posixpath.normpath(display_candidate)
                if display_normalized == normalized_path:
                    continue
                append_unique(others, display_normalized)
                if max_links is not None and len(others) >= max_links:
                    self._display.vvv(
                        f"[read] hardlink scan {label} reached limit with {others}"
                    )
                    return True
            return False

        search_plans = [
            (path_dir, expected_total, True, None, "path_dir_head"),
            (path_dir, None, True, None, "path_dir_full"),
            (search_root, expected_total, True, None, "mount_head"),
            (search_root, None, True, None, "mount_full"),
            (path_dir, None, False, 1, "path_dir_one_level"),
            (path_dir, expected_total, False, 1, "path_dir_one_level_head"),
            (search_root, None, False, None, "mount_crossdev"),
        ]

        for (
            root,
            limit,
            restrict_dev,
            max_depth,
            label,
        ) in search_plans:
            if consume(root, limit, restrict_dev, max_depth, label):
                break
            if max_links is not None and len(others) >= max_links:
                break

        if others:
            return others
        self._display.debug(
            "No hard links found for '%s' after scanning %s",
            path,
            search_root,
        )
        return None

    def _collect_symlink_refs(
        self,
        target: str,
        include_content: bool,
        preferred_encoding: Optional[str],
        task_vars: Optional[Dict[str, Any]],
        parents: bool,
        visited: set[str],
    ) -> Dict[str, Optional[Dict[str, Any]]]:
        """Discover symlinks pointing to a target path and gather metadata."""

        if target in visited:
            return {}

        try:
            stat_result = self._run_action(
                "ansible.builtin.stat",
                {
                    "path": target,
                    "follow": False,
                    "get_attributes": True,
                    "get_checksum": False,
                    "get_mime": False,
                },
                task_vars=task_vars,
            )
        except AnsibleActionFail:
            return {}

        target_stat = stat_result.get("stat", {})
        if not target_stat.get("exists"):
            return {}

        target_type = self._determine_type(target_stat)
        target_inode = self._extract_inode(target_stat)
        follow_stat = self._stat_follow(target, task_vars)
        follow_data = follow_stat.get("stat", {}) if follow_stat else {}
        follow_inode = self._extract_inode(follow_data)

        reference_inodes: set[int] = set()
        if target_inode is not None:
            reference_inodes.add(target_inode)
        if follow_inode is not None:
            reference_inodes.add(follow_inode)

        hard_links_unused, symlink_candidates = self._discover_links(
            path=target,
            task_vars=task_vars,
            inode=target_inode,
            file_type=target_type,
            expected_total=target_stat.get("nlink"),
            include_hardlinks=False,
            include_symlinks=True,
        )
        if not symlink_candidates:
            return {}

        valid_symlinks = self._filter_symlinks(
            candidates=symlink_candidates,
            task_vars=task_vars,
            reference_inodes=reference_inodes,
            current_path=target,
        )
        if not valid_symlinks:
            return {}

        extra: Dict[str, Optional[Dict[str, Any]]] = {}
        for symlink_path in valid_symlinks:
            if symlink_path in visited:
                continue
            symlink_info, nested_extra = self._gather_file_info(
                path=symlink_path,
                include_content=include_content,
                preferred_encoding=preferred_encoding,
                task_vars=task_vars,
                parents=parents,
                find_hardlinks=False,
                find_symlinks=False,
                visited=visited,
            )
            extra.update(nested_extra)
            extra[symlink_path] = symlink_info
            visited.add(symlink_path)
        return extra

    def _collect_parent_paths(
        self, path: str, limit: Optional[int]
    ) -> List[str]:
        """Compute the ordered list of parent directories for a path."""

        if limit is not None and limit <= 0:
            return []

        normalized = posixpath.normpath(path)
        if normalized == posixpath.sep:
            return []

        parents: List[str] = []
        current = normalized

        while True:
            parent = posixpath.dirname(current)
            if parent == current:
                break
            parents.append(parent or posixpath.sep)
            if parent in {"", posixpath.sep}:
                break
            current = parent

        filtered: List[str] = []
        for candidate in parents:
            if candidate in {"", "."}:
                continue
            filtered.append(posixpath.normpath(candidate))

        if filtered:
            if filtered[-1] != posixpath.sep:
                filtered.append(posixpath.sep)
        else:
            filtered.append(posixpath.sep)

        if limit is not None:
            filtered = filtered[:limit]

        filtered.reverse()
        return filtered

    def _process_xattrs(
        self,
        source: Optional[object],
    ) -> Tuple[List[str], List[Dict[str, Any]], Optional[str]]:
        """Normalize xattr sources into names and specialised records."""

        names: List[str] = []
        acl_records: Dict[str, Dict[str, Any]] = {}
        selinux_value: Optional[str] = None

        def place_acl(record_type: str) -> Dict[str, Any]:
            entry = acl_records.setdefault(record_type, {"type": record_type})
            return entry

        def handle(name: str, value: Optional[str]) -> None:
            nonlocal selinux_value
            key = name.strip()
            if not key:
                return
            lowered = key.lower()
            if lowered == "system.posix_acl_access":
                return
            if lowered == "system.posix_acl_default":
                return
            if lowered in {"com.apple.acl.text", "com.apple.security.acl"}:
                entry = place_acl("macos_xattr")
                if value is not None and "text" not in entry:
                    entry["text"] = value
                return
            if lowered in {"system.nfs4_acl", "nfs4_acl"}:
                entry = place_acl("nfs4_xattr")
                if value is not None and "text" not in entry:
                    entry["text"] = value
                return
            if lowered == "security.selinux":
                if value and selinux_value is None:
                    selinux_value = value
                return
            names.append(key)

        if isinstance(source, dict):
            for key, value in source.items():
                if isinstance(key, bytes):
                    key_obj = key.decode("utf-8", "ignore")
                else:
                    key_obj = str(key)
                value_str = None
                if value is not None:
                    if isinstance(value, bytes):
                        value_str = value.decode("utf-8", "ignore")
                    else:
                        value_str = str(value)
                handle(key_obj, value_str)
        elif isinstance(source, str):
            for line in source.splitlines():
                stripped = line.strip()
                if not stripped or stripped.startswith("#"):
                    continue
                if ":" in stripped and "=" not in stripped:
                    key, raw_val = stripped.split(":", 1)
                    handle(key, raw_val.strip())
                    continue
                if "=" in stripped:
                    key, raw_val = stripped.split("=", 1)
                    handle(key, raw_val.strip().strip('"').strip("'"))
                    continue
                handle(stripped, None)
        elif source is not None:
            handle(str(source), None)

        names = sorted(set(names))
        acl_list = [value for value in acl_records.values() if len(value) > 1]
        return names, acl_list, selinux_value

    def _merge_acl(self, info: Dict[str, Any], entry: Dict[str, Any]) -> None:
        """Merge ACL details into result dictionary with type tracking."""

        if not entry:
            return

        entry_type = entry.get("type")
        existing = info.get("acl")

        if entry_type == "posix_xattr":
            if isinstance(existing, dict) and existing.get("type") == "posix":
                return
            if isinstance(existing, list) and any(
                isinstance(item, dict) and item.get("type") == "posix"
                for item in existing
            ):
                return

        if existing is None:
            info["acl"] = entry.copy()
            return

        if isinstance(existing, dict):
            existing_type = existing.get("type")
            if entry_type and existing_type == entry_type:
                merged = existing.copy()
                for key, value in entry.items():
                    if key in {"type"}:
                        continue
                    if key not in merged:
                        merged[key] = value
                info["acl"] = merged
                return

            info["acl"] = [existing.copy(), entry.copy()]
            return

        if isinstance(existing, list):
            if entry_type:
                for idx, item in enumerate(existing):
                    if (
                        isinstance(item, dict)
                        and item.get("type") == entry_type
                    ):
                        merged = item.copy()
                        for key, value in entry.items():
                            if key in {"type"}:
                                continue
                            if key not in merged:
                                merged[key] = value
                        existing[idx] = merged
                        info["acl"] = existing
                        return
            existing.append(entry.copy())
            info["acl"] = existing
            return

        # Existing value is plain string; convert to structured form.
        info["acl"] = [
            {"type": "unknown", "text": str(existing)},
            entry.copy(),
        ]

    def _filter_symlinks(
        self,
        candidates: List[str],
        task_vars: Optional[Dict[str, Any]],
        reference_inodes: set[int],
        current_path: str,
    ) -> List[str]:
        """Filter symlink candidates to those that resolve to the target."""

        valid: List[str] = []
        seen: set[str] = set()
        normalized_current = posixpath.normpath(current_path)

        for candidate in candidates:
            normalized_candidate = posixpath.normpath(candidate)
            if normalized_candidate == normalized_current:
                continue
            if normalized_candidate in seen:
                continue

            follow_stat = self._stat_follow(candidate, task_vars)
            follow_data = follow_stat.get("stat", {}) if follow_stat else {}
            candidate_inode = self._extract_inode(follow_data)
            if reference_inodes and candidate_inode is not None:
                if candidate_inode not in reference_inodes:
                    continue
            elif reference_inodes:
                resolved_path = follow_data.get("path")
                if not resolved_path:
                    continue
                if posixpath.normpath(resolved_path) != normalized_current:
                    continue

            seen.add(normalized_candidate)
            valid.append(normalized_candidate)

        return valid

    def _normalize_flags(self, value: str) -> List[str]:
        """Normalize filesystem flags output into a list."""

        flags = value.strip()
        if not flags or flags == "-":
            return []
        if "," in flags:
            return [flag.strip() for flag in flags.split(",") if flag.strip()]
        return [flag for flag in flags.split() if flag]

    def _get_acl(
        self, path: str, task_vars: Optional[Dict[str, Any]]
    ) -> Optional[Dict[str, Any]]:
        """Retrieve ACL information for a path.

        :param str path: Path to get ACLs for
        :param Optional[Dict[str, Any]] task_vars: Available Ansible
            variables
        :returns Optional[Dict[str, Any]]: ACL metadata with type or None
        """
        result = self._cmd(["getfacl", "-p", path], task_vars=task_vars)
        if result.get("rc") == 0:
            output = (result.get("stdout") or "").strip()
            if output:
                return {"type": "posix", "text": output}
        # macOS fallback: ls -le prints ACLs
        alt = self._cmd(["ls", "-le", path], task_vars=task_vars)
        if alt.get("rc") == 0:
            output = (alt.get("stdout") or "").strip()
            if output:
                lines = output.splitlines()
                prefixes = tuple(f"{i}:" for i in range(10))
                if any(
                    line.lstrip().startswith(prefixes) for line in lines[1:]
                ):
                    return {"type": "macos", "text": output}
        return None

    def _get_xattrs(
        self, path: str, task_vars: Optional[Dict[str, Any]]
    ) -> Optional[str]:
        """Retrieve extended attributes for a path.

        :param str path: Path to get extended attributes for
        :param Optional[Dict[str, Any]] task_vars: Available Ansible
            variables
        :returns Optional[str]: Extended attributes or None if
            unavailable
        """
        result = self._cmd(
            ["getfattr", "--absolute-names", "-d", path], task_vars=task_vars
        )
        if result.get("rc") == 0:
            output = (result.get("stdout") or "").strip()
            if output:
                return output
        # macOS fallback: xattr -l
        alt = self._cmd(["xattr", "-l", path], task_vars=task_vars)
        if alt.get("rc") == 0:
            output = (alt.get("stdout") or "").strip()
            if output:
                return output
        return None

    def _get_flags(
        self, path: str, task_vars: Optional[Dict[str, Any]]
    ) -> Optional[str]:
        """Retrieve filesystem flags for a path.

        :param str path: Path to get flags for
        :param Optional[Dict[str, Any]] task_vars: Available Ansible
            variables
        :returns Optional[str]: Filesystem flags or None if unavailable
        """
        result = self._cmd(["lsattr", "-d", path], task_vars=task_vars)
        if result.get("rc") != 0:
            alt = self._cmd(["ls", "-ldO", path], task_vars=task_vars)
            if alt.get("rc") != 0:
                return None
            stdout = alt.get("stdout") or ""
            parts = stdout.split()
            if len(parts) >= 5:
                flags = parts[4]
                if flags != "-":
                    return flags
            return None
        stdout = result.get("stdout") or ""
        parts = stdout.split()
        if not parts:
            return None
        return parts[0]

    def _detect_encoding(
        self,
        path: str,
        stat_data: Dict[str, Any],
        preferred_encoding: Optional[str],
        task_vars: Optional[Dict[str, Any]],
    ) -> Optional[str]:
        """Detect or validate file encoding for content reading.

        :param str path: Path to detect encoding for
        :param Dict[str, Any] stat_data: Stat module output
        :param Optional[str] preferred_encoding: User-specified encoding
        :param Optional[Dict[str, Any]] task_vars: Available Ansible
            variables
        :returns Optional[str]: Detected or preferred encoding, or None
            if binary
        """
        if preferred_encoding:
            return preferred_encoding

        stat_charset = stat_data.get("charset") or stat_data.get("encoding")
        if stat_charset and stat_charset.lower() not in {"binary", "unknown"}:
            return stat_charset

        result = self._cmd(
            ["file", "-b", "--mime-encoding", path],
            task_vars=task_vars,
        )
        if result.get("rc") == 0:
            guess = (result.get("stdout") or "").strip()
            if guess and guess.lower() not in {"binary", "unknown"}:
                return guess
        return None

    def _maybe_get_content(
        self,
        path: str,
        include_content: bool,
        preferred_encoding: Optional[str],
        stat_data: Dict[str, Any],
        task_vars: Optional[Dict[str, Any]],
    ) -> Tuple[Optional[str], Optional[str]]:
        """Conditionally retrieve and decode file content.

        :param str path: Path to read content from
        :param bool include_content: Whether content reading is
            requested
        :param Optional[str] preferred_encoding: User-specified encoding
        :param Dict[str, Any] stat_data: Stat module output
        :param Optional[Dict[str, Any]] task_vars: Available Ansible
            variables
        :returns Tuple[Optional[str], Optional[str]]: Tuple of
            (encoding, decoded_content)
        :raises AnsibleActionFail: When content decoding fails
        """
        file_type = self._determine_type(stat_data)
        if not include_content or file_type != "regular":
            return None, None

        encoding = self._detect_encoding(
            path=path,
            stat_data=stat_data,
            preferred_encoding=preferred_encoding,
            task_vars=task_vars,
        )
        if not encoding:
            return None, None

        slurp = self._run_action(
            "ansible.builtin.slurp",
            {"src": path},
            task_vars=task_vars,
        )
        content_data = slurp.get("content")
        if not content_data:
            return encoding, None
        try:
            decoded = base64.b64decode(content_data)
            text = decoded.decode(encoding)
        except Exception as exc:
            raise AnsibleActionFail(
                "Failed to decode content from '{path}' using encoding "
                "'{encoding}': {error}".format(
                    path=path,
                    encoding=encoding,
                    error=exc,
                )
            )
        return encoding, text
