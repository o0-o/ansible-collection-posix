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

"""Base class for action plugins that need stat operations."""

from __future__ import annotations

import re
from numbers import Number
from typing import Any, Dict, List, Optional, Tuple

from ansible.module_utils.common.text.converters import to_text

from ansible_collections.o0_o.posix.plugins.module_utils.dev_utils import (
    device_from_hex_major_minor,
    device_from_major_minor,
    device_value,
)
from ansible_collections.o0_o.posix.plugins.module_utils.jc_utils import (
    jc_parse,
)
from ansible_collections.o0_o.posix.plugins.module_utils.posix_action_base import (  # noqa: E501
    PosixActionBase,
)


class ReadPosixActionBase(PosixActionBase):
    """Base class for stat and read plugins with shared methods."""

    def _read(
        self,
        path: Optional[str] = None,
        paths: Optional[list[str]] = None,
        include: Optional[list[str]] = None,
        encoding: Optional[str] = None,
        parents: Optional[bool] = None,
        find_hardlinks: bool = False,
        find_symlinks: bool = False,
        task_vars: Optional[dict[str, Any]] = None,
        check_mode: Optional[bool] = None,
    ) -> dict[str, Any]:
        """
        Run the read action plugin to gather file metadata and
        content.

        Inspects file metadata and optionally content on POSIX hosts
        using portable commands. When path does not exist, returns
        null instead of raising an error.

        :param Optional[str] path: Absolute path to the file to
            inspect
        :param Optional[list[str]] paths: List of paths to inspect
        :param Optional[list[str]] include: List of field names to
            include (metadata, content, type, name, parent, mode,
            owner, group, writable, links, modified, created, acl,
            xattrs, flags, selinux)
        :param Optional[str] encoding: Override detected encoding for
            content
        :param Optional[bool] parents: Include parent directories
            (False, True, or integer count)
        :param bool find_hardlinks: Enumerate all hard link paths
        :param bool find_symlinks: Enumerate all symbolic links
        :param Optional[dict] task_vars: Dictionary of task variables
        :param Optional[bool] check_mode: Optional override for
            Ansible check mode
        :returns dict: Result dictionary with 'paths' containing file
            data
        """
        task_vars = task_vars or {}

        args = {
            "find_hardlinks": find_hardlinks,
            "find_symlinks": find_symlinks,
        }

        if path:
            args["path"] = path
        if paths:
            args["paths"] = paths
        if include:
            args["include"] = include
        if encoding:
            args["encoding"] = encoding
        if parents is not None:
            args["parents"] = parents

        return self._run_action(
            "o0_o.posix.read",
            args,
            task_vars=task_vars,
            check_mode=check_mode,
        )

    def _stat(
        self,
        path: str,
        follow: bool = False,
        get_checksum: bool = True,
        get_mime: bool = True,
        get_attributes: bool = True,
        checksum_algorithm: str = "sha1",
        task_vars: Optional[dict[str, Any]] = None,
        check_mode: Optional[bool] = None,
    ) -> dict[str, Any]:
        """
        Run the stat action plugin to gather file status
        information.

        Retrieves file status information similar to the stat
        command, including permissions, ownership, timestamps,
        checksums, and more.

        :param str path: Path to the file to stat
        :param bool follow: Follow symbolic links (default False)
        :param bool get_checksum: Calculate file checksum (default
            True)
        :param bool get_mime: Get MIME type (default True)
        :param bool get_attributes: Get file attributes (default
            True)
        :param str checksum_algorithm: Algorithm for checksum
            (default sha1)
        :param Optional[dict] task_vars: Dictionary of task variables
        :param Optional[bool] check_mode: Optional override for Ansible
            check mode
        :returns dict: Result dictionary with stat information

        .. note::
           The _force_raw flag is automatically added by _run_action if
           self.force_raw is True, so no need to pass it explicitly.
        """
        task_vars = task_vars or {}

        args = {
            "path": path,
            "follow": follow,
            "get_checksum": get_checksum,
            "get_mime": get_mime,
            "get_attributes": get_attributes,
            "checksum_algorithm": checksum_algorithm,
        }

        return self._run_action(
            "o0_o.posix.stat",
            args,
            task_vars=task_vars,
            check_mode=check_mode,
        )

    def _cat(
        self, src: str, task_vars: Optional[dict[str, Any]] = None
    ) -> dict[str, Any]:
        """
        Fallback method to read the contents of a file using 'cat'.

        :param str src: Path to the file on the remote host
        :param Optional[dict] task_vars: Dictionary of task variables
            from the calling task
        :returns dict: Dictionary with read result or error
        """
        cmd_result = self._cmd(
            ["cat", src], task_vars=task_vars, check_mode=False
        )
        result = {"changed": False, "raw": cmd_result.get("raw", False)}
        result["source"] = src

        stdout = cmd_result.pop("stdout", None)
        stderr = cmd_result.pop("stderr", None)

        if cmd_result.get("rc") != 0:
            result["failed"] = True
            result["msg"] = stderr.strip() or stdout.strip()
        else:
            result["content"] = stdout.replace("\r", "")

        return result

    def _slurp(
        self,
        src: str,
        encoding: str = "utf-8",
        task_vars: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """Run the fallback-compatible slurp64 action plugin.

        Reads remote files using the o0_o.posix.slurp64 action plugin
        which provides Python-free fallback capability.

        :param str src: Path to the file on the remote host
        :param str encoding: File encoding (default: utf-8)
        :param Optional[dict[str, Any]] task_vars: Task variables
        :returns Dict[str, Any]: Result dictionary from slurp64
        """
        return self._run_action(
            "o0_o.posix.slurp64",
            {"src": src, "encoding": encoding},
            task_vars=task_vars,
        )

    def _get_symlink_target(
        self, path: str, task_vars: Optional[dict[str, Any]] = None
    ) -> Optional[str]:
        """Get the immediate target of a symlink using readlink.

        Returns the raw target string as stored in the symlink, which
        may be relative or absolute.

        :param str path: Path to the symlink
        :param Optional[dict[str, Any]] task_vars: Available Ansible
            variables
        :returns Optional[str]: Target path or None if unavailable
        """
        result = self._cmd(
            ["readlink", path], task_vars=task_vars, check_mode=False
        )

        if result.get("rc") == 0:
            output = result.get("stdout", "").strip()
            if output:
                return output

        return None

    def _get_symlink_source(
        self, path: str, task_vars: Optional[dict[str, Any]] = None
    ) -> Optional[str]:
        """Get the fully resolved target of a symlink.

        Follows all intermediate symlinks to find the ultimate target.
        Uses readlink -f which is available on both GNU and BSD systems.

        :param str path: Path to the symlink
        :param Optional[dict[str, Any]] task_vars: Available Ansible
            variables
        :returns Optional[str]: Resolved target path or None
        """
        result = self._cmd(
            ["readlink", "-f", path], task_vars=task_vars, check_mode=False
        )

        if result.get("rc") == 0:
            output = result.get("stdout", "").strip()
            if output:
                return output

        return None

    def _get_stat_commands_stage1(
        self,
        path: str,
        get_mime: bool,
    ) -> dict[str, list[str]]:
        """Generate stage 1 discovery commands with tags.

        Returns tagged commands for initial file discovery including
        stat output, symlink targets, executability, and optionally
        MIME type.

        :param str path: File path to stat
        :param bool get_mime: Whether to include MIME type detection
        :returns dict[str, list[str]]: Dict mapping tags to commands
        """
        commands = {
            "stat_main": ["stat", path],
            "readlink": ["readlink", path],
            "readlink_f": ["readlink", "-f", path],
            "test_x": ["test", "-x", path],
        }

        if get_mime:
            commands["mime"] = ["file", "-b", "--mime", path]

        return commands

    def _get_stat_commands_stage2(
        self,
        path: str,
        username: str,
        groupname: str,
        is_symlink: bool,
        follow: bool,
        file_type_char: str,
        is_regular_file: bool = False,
        get_checksum: bool = False,
        checksum_algorithm: str = "sha1",
        get_attributes: bool = False,
    ) -> dict[str, list[str]]:
        """Generate stage 2 commands based on stage 1 results.

        Returns tagged commands for uid/gid lookup, conditional
        commands based on file type, and optional checksum/attributes.

        :param str path: File path
        :param str username: Owner username from stage 1
        :param str groupname: Owner groupname from stage 1
        :param bool is_symlink: Whether file is symlink (from stage 1)
        :param bool follow: Whether to follow symlinks
        :param str file_type_char: File type character from flags
        :param bool is_regular_file: Whether file is regular (from stage 1)
        :param bool get_checksum: Whether to get checksum
        :param str checksum_algorithm: Checksum algorithm to use
        :param bool get_attributes: Whether to get filesystem attributes
        :returns dict[str, list[str]]: Dict mapping tags to commands
        """
        commands = {
            "uid": ["id", "-u", username],
            "gid": ["id", "-g", username] if username else ["id", "-g"],
        }

        if is_symlink and follow:
            commands["stat_follow"] = ["stat", "-L", path]

        if file_type_char in ("b", "c"):
            commands["device_type"] = ["stat", "-c", "%t,%T", path]

        # Checksum (only for regular files)
        if get_checksum and is_regular_file:
            # Try GNU coreutils commands
            cmd_map = {
                "md5": "md5sum",
                "sha1": "sha1sum",
                "sha224": "sha224sum",
                "sha256": "sha256sum",
                "sha384": "sha384sum",
                "sha512": "sha512sum",
            }
            gnu_cmd = cmd_map.get(checksum_algorithm)
            if gnu_cmd:
                commands["checksum_gnu"] = [gnu_cmd, path]
            # Also try BSD commands as fallback
            commands["checksum_bsd_shasum"] = [
                "shasum",
                "-a",
                checksum_algorithm.replace("sha", ""),
                path,
            ]
            commands["checksum_bsd_md5"] = ["md5", "-q", path]

        # Filesystem attributes
        if get_attributes:
            # Try lsattr first (Linux)
            commands["attrs_lsattr"] = ["lsattr", "-d", path]
            # Try ls -ldO as fallback (BSD/macOS)
            commands["attrs_ls"] = ["ls", "-ldO", path]

        return commands

    def _process_stat_stage1(
        self,
        tagged_results: dict[str, dict[str, Any]],
        path: str,
        follow: bool,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """Process stage 1 results and extract parameters for stage 2.

        Parses stat command output with jc, validates the results, and
        extracts basic file metadata. Returns both a partial stat
        dictionary and parameters needed to generate stage 2 commands.

        :param dict[str, dict[str, Any]] tagged_results: Stage 1
            command results by tag
        :param str path: Original file path
        :param bool follow: Whether to follow symlinks
        :returns tuple[dict[str, Any], dict[str, Any]]: Returns
            (partial_stat, stage2_params) where partial_stat contains
            basic file metadata and stage2_params contains values needed
            for stage 2 command generation
        :raises ValueError: When stat command fails or jc parsing fails
        """
        stat_result = {"exists": False}

        # Check if file exists (stat command succeeded)
        stat_output_result = tagged_results.get("stat_main", {})
        if stat_output_result.get("rc") != 0:
            # File doesn't exist or other error
            return stat_result, {}

        stat_result = {
            "exists": True,
            "attr_flags": "",
            "attributes": [],
        }

        self._display.vvv(stat_output_result.get("stdout"))

        # Parse with jc
        try:
            parsed = jc_parse("stat", stat_output_result.get("stdout", ""))
        except Exception as e:
            raise ValueError(f"Failed to parse stat output for {path}: {e}")

        # Validate jc output
        if (
            not parsed
            or not isinstance(parsed, list)
            or len(parsed) == 0
            or not isinstance(parsed[0], dict)
        ):
            raise ValueError("jc stat parser returned empty result")

        jc_data = parsed[0]
        self._display.vvv(to_text(jc_data))

        # Validate required fields
        for field in ["file", "flags", "user", "group"]:
            if jc_data.get(field) is None or not isinstance(
                jc_data.get(field), str
            ):
                raise ValueError(
                    f"jc stat result missing {field} field (string)"
                )

        for field in [
            "size",
            "links",
            "inode",
            "blocks",
            "access_time_epoch",
            "modify_time_epoch",
            "change_time_epoch",
        ]:
            value = jc_data.get(field)
            if value is None or not isinstance(value, Number):
                raise ValueError(
                    f"jc stat result missing {field} field (number): "
                    f"{to_text(value)}"
                )

        # Extract basic metadata
        result_path = jc_data.get("file")
        if not result_path or not result_path.strip():
            result_path = path

        stat_result["path"] = result_path
        stat_result["size"] = jc_data["size"]
        stat_result["nlink"] = jc_data.get("links")
        stat_result["inode"] = jc_data.get("inode")
        stat_result["dev"] = device_value(jc_data)

        # Handle BSD vs Linux block size differences
        birth_time = jc_data.get("birth_time_epoch")
        if birth_time is not None and not isinstance(birth_time, Number):
            raise ValueError(
                f"jc stat result has invalid birth_time_epoch: "
                f"{to_text(birth_time)}"
            )

        is_bsd = "unix_device" in jc_data
        if is_bsd:
            blocks_value = jc_data.get("blocks", 0)
            block_size_value = jc_data.get("block_size", 512)

            if birth_time is None:
                birth_time_str = jc_data.get("birth_time")
                if birth_time_str and isinstance(birth_time_str, str):
                    try:
                        parsed_block_size = int(birth_time_str)
                        if parsed_block_size > 0:
                            blocks_value = block_size_value
                            block_size_value = parsed_block_size
                    except (ValueError, TypeError):
                        pass

            stat_result["blocks"] = blocks_value
            stat_result["block_size"] = block_size_value
        else:
            stat_result["blocks"] = jc_data.get("blocks", 0)
            block_size = jc_data.get("io_blocks") or jc_data.get("block_size")
            if block_size:
                stat_result["block_size"] = block_size
            else:
                raise ValueError(
                    "jc stat result missing block_size or io_blocks"
                )

        # Timestamps
        stat_result["atime"] = float(jc_data["access_time_epoch"])
        stat_result["mtime"] = float(jc_data["modify_time_epoch"])
        stat_result["ctime"] = float(jc_data["change_time_epoch"])

        if birth_time and birth_time > 0:
            if is_bsd or birth_time != jc_data["change_time_epoch"]:
                stat_result["birthtime"] = float(birth_time)

        # Extract file type info
        flags = jc_data["flags"]
        flags_re = re.compile(r"^[\-dlcbsp][-rwxSsTt]{9}$")
        if not flags_re.match(flags):
            raise ValueError(f"jc flags result invalid: {flags}")

        is_symlink = flags.startswith("l")
        file_type_char = flags[0]
        username = jc_data["user"]
        groupname = jc_data["group"]

        # Store owner names
        stat_result["pw_name"] = username
        stat_result["gr_name"] = groupname

        # BSD unix_flags
        if is_bsd:
            stat_result["flags"] = 0
            unix_flags = jc_data.get("unix_flags")
            if unix_flags and isinstance(unix_flags, str):
                if unix_flags.replace("/", "").replace("x", "").isalnum():
                    try:
                        hex_str = unix_flags.lower().replace("0x", "")
                        if all(c in "0123456789abcdef" for c in hex_str):
                            stat_result["flags"] = int(hex_str, 16)
                    except (ValueError, TypeError):
                        pass

        # Prepare parameters for stage 2
        is_regular_file = flags.startswith("-")

        stage2_params = {
            "username": username,
            "groupname": groupname,
            "is_symlink": is_symlink,
            "follow": follow,
            "file_type_char": file_type_char,
            "is_regular_file": is_regular_file,
            "jc_data": jc_data,  # Pass full jc_data for stage 2
            "flags": flags,
            "is_bsd": is_bsd,
        }

        return stat_result, stage2_params

    def _process_stat_stage2(
        self,
        tagged_results: dict[str, dict[str, Any]],
        stage1_tagged_results: dict[str, dict[str, Any]],
        partial_stat: dict[str, Any],
        stage2_params: dict[str, Any],
        path: str,
        get_checksum: bool,
        checksum_algorithm: str,
        get_mime: bool,
        get_attributes: bool,
        task_vars: dict[str, Any],
    ) -> dict[str, Any]:
        """Process stage 2 results and finalize stat dictionary.

        Takes stage 2 command results and merges them with partial
        stat from stage 1 to create the final complete stat structure
        matching ansible.builtin.stat format.

        :param dict[str, dict[str, Any]] tagged_results: Stage 2
            command results by tag
        :param dict[str, dict[str, Any]] stage1_tagged_results: Stage 1
            results for re-use
        :param dict[str, Any] partial_stat: Partial stat from stage 1
        :param dict[str, Any] stage2_params: Parameters from stage 1
        :param str path: File path
        :param bool get_checksum: Whether to compute checksum
        :param str checksum_algorithm: Checksum algorithm
        :param bool get_mime: Whether MIME was requested
        :param bool get_attributes: Whether to get attributes
        :param dict[str, Any] task_vars: Task variables
        :returns dict[str, Any]: Complete stat dictionary
        :raises ValueError: When required commands fail
        """
        stat_result = partial_stat.copy()

        # Extract stage 2 parameters
        jc_data = stage2_params["jc_data"]
        flags = stage2_params["flags"]
        is_symlink = stage2_params["is_symlink"]
        follow = stage2_params["follow"]

        # Get uid/gid from stage 2 results
        uid_result = tagged_results.get("uid", {})
        gid_result = tagged_results.get("gid", {})

        if uid_result.get("rc") == 0:
            uid_str = uid_result.get("stdout", "").strip()
            if uid_str and uid_str.isdigit():
                stat_result["uid"] = int(uid_str)
        else:
            username = stage2_params["username"]
            raise ValueError(f"Unable to determine uid of {username}")

        if gid_result.get("rc") == 0:
            gid_str = gid_result.get("stdout", "").strip()
            if gid_str and gid_str.isdigit():
                stat_result["gid"] = int(gid_str)
        else:
            groupname = stage2_params["groupname"]
            raise ValueError(f"Unable to determine gid of {groupname}")

        # Get device_type if requested
        device_result_for_type = tagged_results.get("device_type")
        stat_result["device_type"] = self._stat_device_type(
            jc_data, device_result=device_result_for_type
        )

        # Handle symlink following
        target_jc_data = None
        if is_symlink and follow:
            stat_follow_result = tagged_results.get("stat_follow")
            if not stat_follow_result:
                raise ValueError("stat -L should have been in stage 2")

            try:
                target_parsed = jc_parse(
                    "stat", stat_follow_result.get("stdout", "")
                )
                if not target_parsed or not isinstance(target_parsed, list):
                    raise ValueError(
                        "jc stat parser returned empty result for target"
                    )
                target_jc_data = target_parsed[0]
                if not isinstance(target_jc_data, dict):
                    raise ValueError(
                        "jc stat parser returned invalid result for target"
                    )
                if not target_jc_data.get("flags") or not isinstance(
                    target_jc_data.get("flags"), str
                ):
                    raise ValueError(
                        "jc stat result for target missing flags field"
                    )
                # Check for broken symlink
                if target_jc_data["flags"].startswith("l"):
                    return {"exists": False}
            except ValueError:
                raise
            except Exception as e:
                raise ValueError(
                    f"Failed to parse stat output for target {path}: {e}"
                )

        # Set file type flags
        type_flags = target_jc_data["flags"] if target_jc_data else flags

        stat_result["isdir"] = type_flags.startswith("d")
        stat_result["islnk"] = type_flags.startswith("l")
        stat_result["isreg"] = type_flags.startswith("-")
        stat_result["isblk"] = type_flags.startswith("b")
        stat_result["ischr"] = type_flags.startswith("c")
        stat_result["isfifo"] = type_flags.startswith("p")
        stat_result["issock"] = type_flags.startswith("s")

        # Check executability from stage 1
        test_x_result = stage1_tagged_results.get("test_x", {})
        is_executable = test_x_result.get("rc") == 0

        # Mode
        mode_flags = target_jc_data["flags"] if target_jc_data else flags
        stat_result["mode"] = self._stat_mode_from_flags(mode_flags)

        # Permission booleans
        permission_bools = self._stat_permission_booleans(mode_flags)
        permission_bools["executable"] = is_executable
        stat_result.update(permission_bools)

        # Symlink targets from stage 1
        if is_symlink:
            readlink_result = stage1_tagged_results.get("readlink", {})
            readlink_f_result = stage1_tagged_results.get("readlink_f", {})

            if readlink_result.get("rc") == 0:
                lnk_target = readlink_result.get("stdout", "").strip()
                if lnk_target:
                    stat_result["lnk_target"] = lnk_target

            if readlink_f_result.get("rc") == 0:
                lnk_source = readlink_f_result.get("stdout", "").strip()
                if lnk_source:
                    stat_result["lnk_source"] = lnk_source

        # Checksum for regular files (from stage 2 results)
        if get_checksum and stat_result["isreg"]:
            checksum = self._parse_checksum_from_results(
                tagged_results, checksum_algorithm
            )
            if checksum:
                stat_result["checksum"] = checksum
            else:
                self._display.warning(
                    f"[{self.inventory_hostname}] Checksum algorithm "
                    f"'{checksum_algorithm}' not available on target system. "
                    f"Checksum field will be omitted."
                )

        # MIME type from stage 1
        if get_mime:
            mime_result = stage1_tagged_results.get("mime")
            if mime_result:
                if mime_result.get("rc") == 0:
                    output = mime_result.get("stdout", "").strip()
                    if output:
                        mime_info: dict[str, str] = {}
                        parts = output.split(";", 1)
                        if parts:
                            mimetype = parts[0].strip()
                            if mimetype == "application/x-not-regular-file":
                                mime_info["mimetype"] = "unknown"
                            else:
                                mime_info["mimetype"] = mimetype

                        if len(parts) > 1:
                            charset_part = parts[1].strip()
                            if charset_part.startswith("charset="):
                                mime_info["charset"] = charset_part[8:].strip()

                        if "charset" not in mime_info:
                            mime_info["charset"] = "unknown"

                        if mime_info:
                            stat_result.update(mime_info)
                        else:
                            raise ValueError("MIME info is empty")
                    else:
                        raise ValueError("MIME output is empty")
                else:
                    raise ValueError(
                        f"MIME command failed: {mime_result.get('stderr', '')}"
                    )

        # Extended attributes (from stage 2 results)
        if get_attributes:
            flags_output = self._parse_attributes_from_results(tagged_results)
            if flags_output:
                attr_flags_raw = self._extract_attr_flags(flags_output)
                if attr_flags_raw:
                    stat_result["attr_flags"] = attr_flags_raw

                if attr_flags_raw:
                    attrs = self._normalize_flags(flags_output)
                    if attrs:
                        stat_result["attributes"] = attrs

        return stat_result

    def _parse_checksum_from_results(
        self,
        tagged_results: dict[str, dict[str, Any]],
        algorithm: str,
    ) -> Optional[str]:
        """Parse checksum from stage 2 command results.

        Tries to extract checksum from various command results (GNU
        coreutils, BSD shasum, BSD md5) based on which commands
        succeeded.

        :param dict[str, dict[str, Any]] tagged_results: Stage 2 results
        :param str algorithm: Checksum algorithm requested
        :returns Optional[str]: Hex checksum string or None
        """
        # Try GNU coreutils command first
        gnu_result = tagged_results.get("checksum_gnu", {})
        if gnu_result.get("rc") == 0:
            output = gnu_result.get("stdout", "").strip()
            if output:
                # GNU format: "checksum  filename"
                parts = output.split()
                if parts:
                    return parts[0]

        # Try BSD shasum command
        if algorithm.startswith("sha"):
            shasum_result = tagged_results.get("checksum_bsd_shasum", {})
            if shasum_result.get("rc") == 0:
                output = shasum_result.get("stdout", "").strip()
                if output:
                    parts = output.split()
                    if parts:
                        return parts[0]

        # Try BSD md5 command
        if algorithm == "md5":
            md5_result = tagged_results.get("checksum_bsd_md5", {})
            if md5_result.get("rc") == 0:
                output = md5_result.get("stdout", "").strip()
                if output:
                    # BSD md5 outputs just the hash
                    return output

        return None

    def _parse_attributes_from_results(
        self,
        tagged_results: dict[str, dict[str, Any]],
    ) -> Optional[str]:
        """Parse filesystem attributes from stage 2 command results.

        Tries to extract attributes from lsattr (Linux) or ls -ldO
        (BSD/macOS) command results.

        :param dict[str, dict[str, Any]] tagged_results: Stage 2 results
        :returns Optional[str]: Attribute flags string or None
        """
        # Try lsattr first (Linux)
        lsattr_result = tagged_results.get("attrs_lsattr", {})
        if lsattr_result.get("rc") == 0:
            stdout = lsattr_result.get("stdout", "")
            parts = stdout.split()
            if parts:
                return parts[0]

        # Try ls -ldO fallback (BSD/macOS)
        ls_result = tagged_results.get("attrs_ls", {})
        if ls_result.get("rc") == 0:
            stdout = ls_result.get("stdout", "")
            parts = stdout.split()
            if len(parts) >= 5:
                flags = parts[4]
                if flags != "-":
                    return flags

        return None

    def _get_checksum(
        self,
        path: str,
        algorithm: str,
        task_vars: Optional[dict[str, Any]],
    ) -> Optional[str]:
        """Compute file checksum using available hash commands.

        :param str path: File path to checksum
        :param str algorithm: Hash algorithm (md5, sha1, sha224, sha256,
            sha384, sha512)
        :param Optional[dict[str, Any]] task_vars: Available Ansible
            variables
        :returns Optional[str]: Hex checksum string or None
        """
        # Try GNU coreutils first (Linux)
        cmd_map_gnu = {
            "md5": "md5sum",
            "sha1": "sha1sum",
            "sha224": "sha224sum",
            "sha256": "sha256sum",
            "sha384": "sha384sum",
            "sha512": "sha512sum",
        }

        gnu_cmd = cmd_map_gnu.get(algorithm)
        if gnu_cmd:
            result = self._cmd(
                [gnu_cmd, path], task_vars=task_vars, check_mode=False
            )
            if result.get("rc") == 0:
                stdout = result.get("stdout", "").strip()
                if stdout:
                    # Format: "checksum  filename"
                    parts = stdout.split()
                    if parts:
                        return parts[0]

        # Try BSD/macOS commands
        if algorithm == "md5":
            result = self._cmd(
                ["md5", "-q", path], task_vars=task_vars, check_mode=False
            )
            if result.get("rc") == 0:
                return result.get("stdout", "").strip()

        # Try shasum (available on macOS and some Linux)
        if algorithm in ("sha1", "sha224", "sha256", "sha384", "sha512"):
            algo_num = {
                "sha1": "1",
                "sha224": "224",
                "sha256": "256",
                "sha384": "384",
                "sha512": "512",
            }[algorithm]
            result = self._cmd(
                ["shasum", "-a", algo_num, path],
                task_vars=task_vars,
                check_mode=False,
            )
            if result.get("rc") == 0:
                stdout = result.get("stdout", "").strip()
                if stdout:
                    parts = stdout.split()
                    if parts:
                        return parts[0]

        # Try OpenBSD commands (sha1, sha256, sha512 without -q)
        # Output format: "SHA256 (file) = checksum"
        if algorithm in ("sha1", "sha256", "sha512"):
            result = self._cmd(
                [algorithm, path], task_vars=task_vars, check_mode=False
            )
            if result.get("rc") == 0:
                stdout = result.get("stdout", "").strip()
                if stdout and "=" in stdout:
                    # Parse "SHA256 (file) = checksum"
                    checksum = stdout.split("=", 1)[1].strip()
                    if checksum:
                        return checksum

        return None

    def _get_mime(
        self, path: str, task_vars: Optional[dict[str, Any]]
    ) -> Optional[dict[str, str]]:
        """Detect MIME type and charset.

        :param str path: File path to inspect
        :param Optional[dict[str, Any]] task_vars: Available Ansible
            variables
        :returns Optional[dict[str, str]]: Dict with mimetype and
            charset or None
        """
        result = self._cmd(
            ["file", "-b", "--mime", path],
            task_vars=task_vars,
            check_mode=False,
        )
        if result.get("rc") != 0:
            return None

        output = result.get("stdout", "").strip()
        if not output:
            return None

        # Parse: "text/plain; charset=us-ascii"
        mime_info: dict[str, str] = {}
        parts = output.split(";", 1)
        if parts:
            mimetype = parts[0].strip()
            # Normalize application/x-not-regular-file to "unknown" to
            # match builtin.stat behavior on OpenBSD
            if mimetype == "application/x-not-regular-file":
                mime_info["mimetype"] = "unknown"
            else:
                mime_info["mimetype"] = mimetype

        if len(parts) > 1:
            charset_part = parts[1].strip()
            if charset_part.startswith("charset="):
                mime_info["charset"] = charset_part[8:].strip()

        # Always include charset, default to "unknown" if not found
        if "charset" not in mime_info:
            mime_info["charset"] = "unknown"

        return mime_info if mime_info else None

    def _stat_device_type(
        self,
        jc_data: dict[str, Any],
        device_result: Optional[dict[str, Any]] = None,
    ) -> int:
        """Get device type (rdev) with intelligent fallback detection.

        Determines the device type value based on file type and
        available data. For regular files and similar types, returns 0.
        For device files, uses the provided device_result from batched
        command execution.

        :param Dict[str, Any] jc_data: Parsed jc stat output
        :param Optional[dict[str, Any]] device_result: Result from
            stat -c "%t,%T" command (if device file)
        :returns int: Device type number (rdev), 0 for non-device
            files
        """
        # If jc already parsed rdev, use it
        rdev = jc_data.get("rdev")
        if rdev is not None:
            # Convert if needed (decimal major,minor format)
            if isinstance(rdev, str) and "," in rdev:
                rdev_int = device_from_major_minor(rdev)
                if rdev_int is not None:
                    return rdev_int
            # Direct integer or convertible string
            try:
                return int(rdev) if rdev else 0
            except (ValueError, TypeError):
                pass

        # Determine file type from flags to decide if we need rdev
        flags = jc_data.get("flags", "")
        if not flags:
            return 0

        file_type_char = flags[0]

        # File types that always have rdev=0
        # - regular file, d directory, l symlink, p fifo, s socket
        if file_type_char in ("-", "d", "l", "p", "s"):
            return 0

        # Block or character device - use provided device_result
        if file_type_char in ("b", "c") and device_result:
            if device_result.get("rc") == 0:
                output = device_result.get("stdout", "").strip()
                if output:
                    rdev_int = device_from_hex_major_minor(output)
                    if rdev_int is not None:
                        return rdev_int

        # Default fallback
        return 0

    def _stat_mode_from_flags(self, flags: str) -> str:
        """Convert permission flags to 4-digit octal mode.

        Parses Unix permission flags (e.g., "-rw-r--r--") and converts
        them to 4-digit octal format (e.g., "0644").

        :param str flags: Permission flags string from stat
        :returns str: 4-digit octal mode string
        """
        if not flags or len(flags) < 10:
            return "0000"

        mode = 0

        # Special bits (setuid, setgid, sticky)
        if flags[3] in ("s", "S"):  # setuid
            mode |= 0o4000
        if flags[6] in ("s", "S"):  # setgid
            mode |= 0o2000
        if flags[9] in ("t", "T"):  # sticky
            mode |= 0o1000

        # Owner permissions
        if flags[1] == "r":
            mode |= 0o400
        if flags[2] == "w":
            mode |= 0o200
        if flags[3] in ("x", "s"):
            mode |= 0o100

        # Group permissions
        if flags[4] == "r":
            mode |= 0o040
        if flags[5] == "w":
            mode |= 0o020
        if flags[6] in ("x", "s"):
            mode |= 0o010

        # Other permissions
        if flags[7] == "r":
            mode |= 0o004
        if flags[8] == "w":
            mode |= 0o002
        if flags[9] in ("x", "t"):
            mode |= 0o001

        return f"{mode:04o}"

    def _stat_permission_booleans(self, flags: str) -> dict[str, bool]:
        """Parse permission booleans from flags string.

        :param str flags: Permission flags string (e.g., "-rw-r--r--")
        :returns Dict[str, bool]: Permission boolean dictionary
        """
        if not flags or len(flags) < 10:
            return {}

        perms: dict[str, bool] = {}

        # Owner permissions
        perms["rusr"] = flags[1] == "r"
        perms["wusr"] = flags[2] == "w"
        perms["xusr"] = flags[3] in ("x", "s")

        # Group permissions
        perms["rgrp"] = flags[4] == "r"
        perms["wgrp"] = flags[5] == "w"
        perms["xgrp"] = flags[6] in ("x", "s")

        # Other permissions
        perms["roth"] = flags[7] == "r"
        perms["woth"] = flags[8] == "w"
        perms["xoth"] = flags[9] in ("x", "t")

        # Special bits
        perms["isuid"] = flags[3] in ("s", "S")
        perms["isgid"] = flags[6] in ("s", "S")

        # High-level permission flags (simplified)
        perms["readable"] = perms["rusr"]
        perms["writeable"] = perms["wusr"]
        perms["executable"] = perms["xusr"]

        return perms

    def _validate_jc_stat_result(self, jc_data: dict[str, Any]) -> None:
        """Validate that jc stat result has required fields.

        :param Dict[str, Any] jc_data: Parsed jc stat output
        :raises ValueError: If required fields are missing or invalid
        """
        for field in ["file", "flags", "user", "group"]:
            if jc_data.get(field) is None or not isinstance(
                jc_data.get(field), str
            ):
                raise ValueError(
                    f"jc stat result missing {field} field (string)"
                )

        for field in [
            "size",
            "links",
            "inode",
            "blocks",
            "access_time_epoch",
            "modify_time_epoch",
            "change_time_epoch",
        ]:
            value = jc_data.get(field)
            if value is None or not isinstance(value, Number):
                raise ValueError(
                    f"jc stat result missing {field} field (number): {value}"
                )

        # birth_time_epoch is optional - not all systems support it
        birth_time = jc_data.get("birth_time_epoch")
        if birth_time is not None and not isinstance(birth_time, Number):
            raise ValueError(
                f"jc stat result has invalid birth_time_epoch: "
                f"{birth_time}"
            )

        # Validate flags format
        flags = jc_data["flags"]
        flags_re = re.compile(r"^[\-dlcbsp][-rwxSsTt]{9}$")
        if not flags_re.match(flags):
            raise ValueError(f"jc flags result invalid: {flags}")

    def _get_acl(
        self, path: str, task_vars: Optional[dict[str, Any]]
    ) -> Optional[dict[str, Any]]:
        """Retrieve ACL information for a path.

        :param str path: Path to get ACLs for
        :param Optional[dict[str, Any]] task_vars: Available Ansible
            variables
        :returns Optional[dict[str, Any]]: ACL metadata with type or
            None
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
        self, path: str, task_vars: Optional[dict[str, Any]]
    ) -> Optional[str]:
        """Retrieve extended attributes for a path.

        :param str path: Path to get extended attributes for
        :param Optional[dict[str, Any]] task_vars: Available Ansible
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
        self, path: str, task_vars: Optional[dict[str, Any]]
    ) -> Optional[str]:
        """Retrieve filesystem flags for a path.

        :param str path: Path to get flags for
        :param Optional[dict[str, Any]] task_vars: Available Ansible
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

    def _process_xattrs(
        self,
        source: Optional[object],
    ) -> Tuple[List[str], List[Dict[str, Any]], Optional[str]]:
        """Normalize xattr sources into names and specialised records.

        :param Optional[object] source: Extended attributes from xattr
            command
        :returns Tuple[List[str], List[Dict[str, Any]], Optional[str]]:
            Tuple of (attribute names, ACL records, SELinux value)
        """
        names: list[str] = []
        acl_records: dict[str, Dict[str, Any]] = {}
        selinux_value: Optional[str] = None

        def place_acl(record_type: str) -> dict[str, Any]:
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

    def _merge_acl(self, info: dict[str, Any], entry: dict[str, Any]) -> None:
        """Merge ACL details into result dictionary with type tracking.

        :param Dict[str, Any] info: Stat dictionary to merge ACL into
        :param Dict[str, Any] entry: ACL entry to merge
        """
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

    def _extract_attr_flags(self, value: str) -> str:
        """Extract raw flag characters from lsattr output.

        Converts "--------------e-------" to "e" (just the set flags).
        For BSD/macOS format, returns empty string as it doesn't use
        single-character flags.

        :param str value: Raw lsattr/ls output
        :returns str: Flag characters that are set
        """
        flags_str = value.strip()
        if not flags_str or flags_str == "-":
            return ""

        # BSD/macOS format - doesn't use attr_flags field
        if "," in flags_str or any(
            word.isalpha() and len(word) > 1 for word in flags_str.split()
        ):
            return ""

        # Linux lsattr format - extract non-dash characters
        flag_chars = "".join(
            char for char in flags_str if char not in ("-", " ")
        )
        return flag_chars

    def _normalize_flags(self, value: str) -> list[str]:
        """Parse filesystem flags into attribute names.

        Handles multiple formats:
        - Linux lsattr: "--------------e-------" → ["extents"]
        - BSD/macOS: "restricted,hidden" or "restricted hidden" → as-is

        :param str value: Raw flags string
        :returns List[str]: List of attribute names
        """
        flags_str = value.strip()
        if not flags_str or flags_str == "-":
            return []

        # BSD/macOS format: comma or space separated words
        if "," in flags_str:
            return [
                flag.strip() for flag in flags_str.split(",") if flag.strip()
            ]

        # Check if readable words (BSD format without commas)
        if any(word.isalpha() and len(word) > 1 for word in flags_str.split()):
            return [flag.strip() for flag in flags_str.split() if flag.strip()]

        # Linux lsattr format: single-character flags
        flag_map = {
            "a": "append_only",
            "c": "compressed",
            "d": "no_dump",
            "e": "extents",
            "i": "immutable",
            "j": "data_journaling",
            "s": "secure_deletion",
            "t": "no_tail_merging",
            "u": "undeletable",
            "A": "no_atime",
            "D": "synchronous_directory",
            "S": "synchronous_updates",
            "T": "top_of_directory_hierarchy",
            "C": "no_copy_on_write",
            "E": "encrypted",
            "I": "indexed_directory",
            "N": "inline_data",
            "P": "project_hierarchy",
            "V": "verity",
        }

        attributes = []
        for char in flags_str:
            if char in flag_map:
                attributes.append(flag_map[char])

        return attributes
