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

import base64
from os.path import join
from typing import Any, Optional

from ansible_collections.o0_o.posix.plugins.module_utils.jc_utils import (
    jc_parse,
)
from ansible_collections.o0_o.posix.plugins.module_utils.path_utils import (
    flags_to_octal_mode,
)
from ansible_collections.o0_o.posix.plugins.module_utils.posix_action_base import (  # noqa: E501
    PosixActionBase,
)
from ansible_collections.o0_o.utils.plugins.module_utils import (
    format_epoch_timestamp,
    parse_si,
    unflatten,
)


class ReadPosixActionBase(PosixActionBase):
    """Base class for stat and read plugins with shared methods."""

    def _read(
        self,
        paths: Any,
        task_vars: Optional[dict[str, Any]] = None,
        check_mode: Optional[bool] = None,
        **options: Any,
    ) -> dict[str, Any]:
        """Run the o0_o.posix.read action for one or more paths.

        Metadata (type, mode, owner, group, timestamps, ACL, SELinux)
        arrives by default through the read action's attributes
        option. Extra keyword options pass through to its argument
        spec (extended, content, follow, children, ...).

        :param paths: Path or list of paths to inspect
        :param Optional[dict] task_vars: Dictionary of task variables
            from the calling task
        :param Optional[bool] check_mode: Override check mode setting
        :param options: Additional read action arguments
        :returns dict: The read action's result, with metadata under
            its paths key
        """
        if isinstance(paths, str):
            paths = [paths]

        args: dict[str, Any] = {"paths": paths}
        args.update(options)

        return self._run_action(
            "o0_o.posix.read",
            args,
            task_vars=task_vars,
            check_mode=check_mode,
        )

    def _get_read_commands(
        self,
        paths: list[str],
        options: dict[str, Any],
        need_dir_contents: bool = False,
        platform: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """
        Generate batched commands to inspect multiple paths.

        Uses ls -dn as the base command for each path. Additional
        commands are added based on the options dict and platform
        capabilities.

        :param list[str] paths: Paths to inspect
        :param dict[str, Any] options: Options dict with keys: attributes,
            extended, content, encoding, mime, md5, sha1, sha256, sha512
        :param bool need_dir_contents: If True, add commands to list
            directory contents (for children feature)
        :param Optional[dict[str, Any]] platform: Platform capabilities
            dict from _detect_platform_from_results(). If None, generates
            all command variants for detection on first file.
        :returns dict: Command dictionary keyed by path-prefixed tags
        """
        commands: dict[str, Any] = {}
        include_attributes = options.get("attributes", False) or options.get(
            "extended", False
        )
        include_extended = options.get("extended", False)
        include_content = options.get("content", False) or options.get(
            "lines", False
        )
        forced_encoding = options.get("encoding")
        include_mime = options.get("mime", False)
        include_md5 = options.get("md5", False)
        include_sha1 = options.get("sha1", False)
        include_sha256 = options.get("sha256", False)
        include_sha512 = options.get("sha512", False)

        # Extract platform capabilities (None = detection mode, run all)
        # TODO: In the future, check for cached platform facts from
        # o0_os['platform'] before falling back to detection mode.
        stat_variant = platform.get("stat_variant") if platform else None
        has_lsattr = platform.get("has_lsattr", False) if platform else None
        has_getfacl = platform.get("has_getfacl", False) if platform else None
        has_nfs4_getfacl = (
            platform.get("has_nfs4_getfacl", False) if platform else None
        )
        has_getfattr = (
            platform.get("has_getfattr", False) if platform else None
        )
        has_xattr = platform.get("has_xattr", False) if platform else None
        ls_supports_selinux = (
            platform.get("ls_supports_selinux", False) if platform else None
        )
        ls_supports_acl_macos = (
            platform.get("ls_supports_acl_macos", False) if platform else None
        )
        ls_supports_flags_bsd = (
            platform.get("ls_supports_flags_bsd", False) if platform else None
        )

        for path in paths:
            # Basic file info using ls -dn (numeric UIDs/GIDs)
            commands[f"{path}_ls"] = ["ls", "-dn", path]

            # Inode for hardlink identification - use detected variant
            if stat_variant is None:
                # Detection mode: run both
                commands[f"{path}_inode"] = ["stat", "-c", "%i", path]
                commands[f"{path}_inode_bsd"] = ["stat", "-f", "%i", path]
            elif stat_variant == "gnu":
                commands[f"{path}_inode"] = ["stat", "-c", "%i", path]
            else:  # bsd
                commands[f"{path}_inode_bsd"] = ["stat", "-f", "%i", path]

            # Timestamps if attributes requested
            if include_attributes:
                if stat_variant is None:
                    # Detection mode: run both
                    commands[f"{path}_stat"] = [
                        "stat",
                        "-c",
                        "%Y %Z %W",
                        path,
                    ]
                    commands[f"{path}_stat_bsd"] = [
                        "stat",
                        "-f",
                        "%m %c %B",
                        path,
                    ]
                elif stat_variant == "gnu":
                    commands[f"{path}_stat"] = [
                        "stat",
                        "-c",
                        "%Y %Z %W",
                        path,
                    ]
                else:  # bsd
                    commands[f"{path}_stat_bsd"] = [
                        "stat",
                        "-f",
                        "%m %c %B",
                        path,
                    ]

            # File content reading if requested
            if include_content:
                # Only auto-detect encoding if not forced
                if not forced_encoding:
                    # Try GNU, BSD, and basic file command variants
                    # GNU: file -b --mime-encoding
                    commands[f"{path}_encoding"] = [
                        "file",
                        "-b",
                        "--mime-encoding",
                        path,
                    ]
                    # FreeBSD/macOS: file -b -I
                    commands[f"{path}_encoding_bsd"] = [
                        "file",
                        "-b",
                        "-I",
                        path,
                    ]
                    # OpenBSD/fallback: file -b (descriptive text)
                    commands[f"{path}_encoding_desc"] = ["file", "-b", path]
                # Always need cat to read the content
                commands[f"{path}_cat"] = ["cat", path]

            # MIME type detection if requested
            if include_mime:
                # Try both GNU and BSD file command variants
                commands[f"{path}_mimetype"] = [
                    "file",
                    "-b",
                    "--mime-type",
                    path,
                ]
                commands[f"{path}_mimetype_bsd"] = ["file", "-b", "-I", path]

            # Hash checksums if requested
            # Try multiple hash command variants for platform detection
            if include_md5:
                if platform is None:
                    # Detection mode: try both GNU and BSD variants
                    commands[f"{path}_md5"] = ["md5sum", path]
                    commands[f"{path}_md5_bsd"] = ["md5", "-q", path]
                elif platform.get("has_md5sum"):
                    commands[f"{path}_md5"] = ["md5sum", path]
                elif platform.get("has_md5_bsd"):
                    commands[f"{path}_md5_bsd"] = ["md5", "-q", path]

            if include_sha1:
                if platform is None:
                    commands[f"{path}_sha1"] = ["sha1sum", path]
                    commands[f"{path}_sha1_shasum"] = [
                        "shasum",
                        "-a",
                        "1",
                        path,
                    ]
                    commands[f"{path}_sha1_bsd"] = ["sha1", "-q", path]
                elif platform.get("has_sha1sum"):
                    commands[f"{path}_sha1"] = ["sha1sum", path]
                elif platform.get("has_shasum"):
                    commands[f"{path}_sha1_shasum"] = [
                        "shasum",
                        "-a",
                        "1",
                        path,
                    ]
                elif platform.get("has_sha1_bsd"):
                    commands[f"{path}_sha1_bsd"] = ["sha1", "-q", path]

            if include_sha256:
                if platform is None:
                    commands[f"{path}_sha256"] = ["sha256sum", path]
                    commands[f"{path}_sha256_shasum"] = [
                        "shasum",
                        "-a",
                        "256",
                        path,
                    ]
                    commands[f"{path}_sha256_bsd"] = ["sha256", "-q", path]
                elif platform.get("has_sha256sum"):
                    commands[f"{path}_sha256"] = ["sha256sum", path]
                elif platform.get("has_shasum"):
                    commands[f"{path}_sha256_shasum"] = [
                        "shasum",
                        "-a",
                        "256",
                        path,
                    ]
                elif platform.get("has_sha256_bsd"):
                    commands[f"{path}_sha256_bsd"] = ["sha256", "-q", path]

            if include_sha512:
                if platform is None:
                    commands[f"{path}_sha512"] = ["sha512sum", path]
                    commands[f"{path}_sha512_shasum"] = [
                        "shasum",
                        "-a",
                        "512",
                        path,
                    ]
                    commands[f"{path}_sha512_bsd"] = ["sha512", "-q", path]
                elif platform.get("has_sha512sum"):
                    commands[f"{path}_sha512"] = ["sha512sum", path]
                elif platform.get("has_shasum"):
                    commands[f"{path}_sha512_shasum"] = [
                        "shasum",
                        "-a",
                        "512",
                        path,
                    ]
                elif platform.get("has_sha512_bsd"):
                    commands[f"{path}_sha512_bsd"] = ["sha512", "-q", path]

            # ACL info if attributes requested
            if include_attributes:
                if has_getfacl is None:
                    # Detection mode: run all ACL variants
                    commands[f"{path}_acl"] = ["getfacl", "-p", path]
                    commands[f"{path}_acl_nfs4"] = ["nfs4_getfacl", path]
                    commands[f"{path}_acl_macos"] = ["ls", "-le", path]
                elif has_getfacl:
                    commands[f"{path}_acl"] = ["getfacl", "-p", path]
                elif has_nfs4_getfacl:
                    commands[f"{path}_acl_nfs4"] = ["nfs4_getfacl", path]
                elif ls_supports_acl_macos:
                    commands[f"{path}_acl_macos"] = ["ls", "-le", path]
                # else: no ACL command available, skip

            # Extended attributes if extended requested
            if include_extended:
                if has_getfattr is None:
                    # Detection mode: run both
                    commands[f"{path}_xattr"] = [
                        "getfattr",
                        "--absolute-names",
                        "-d",
                        path,
                    ]
                    # Use -lx for hex output (avoids binary corruption)
                    commands[f"{path}_xattr_macos"] = ["xattr", "-lx", path]
                elif has_getfattr:
                    commands[f"{path}_xattr"] = [
                        "getfattr",
                        "--absolute-names",
                        "-d",
                        path,
                    ]
                elif has_xattr:
                    # Use -lx for hex output (avoids binary corruption)
                    commands[f"{path}_xattr_macos"] = ["xattr", "-lx", path]
                # else: no xattr command available, skip

            # Filesystem flags if attributes requested
            if include_attributes:
                if has_lsattr is None:
                    # Detection mode: run both
                    commands[f"{path}_flags"] = ["lsattr", "-d", path]
                    commands[f"{path}_flags_macos"] = ["ls", "-ldO", path]
                elif has_lsattr:
                    commands[f"{path}_flags"] = ["lsattr", "-d", path]
                elif ls_supports_flags_bsd:
                    commands[f"{path}_flags_macos"] = ["ls", "-ldO", path]
                # else: no flags command available, skip

            # SELinux context if attributes requested
            if include_attributes:
                if ls_supports_selinux is None:
                    # Detection mode: run both
                    commands[f"{path}_selinux"] = ["stat", "-c", "%C", path]
                    commands[f"{path}_selinux_ls"] = ["ls", "-Zd", path]
                elif stat_variant == "gnu":
                    # GNU stat supports %C for SELinux
                    commands[f"{path}_selinux"] = ["stat", "-c", "%C", path]
                elif ls_supports_selinux:
                    commands[f"{path}_selinux_ls"] = ["ls", "-Zd", path]
                # else: no SELinux support, skip

            # Directory listing if needed
            if need_dir_contents:
                commands[f"{path}_contents"] = ["ls", "-1A", path]

        return commands

    def _detect_platform_from_results(
        self,
        results: dict[str, Any],
        path: str,
    ) -> dict[str, Any]:
        """
        Detect platform capabilities from first file's command results.

        Analyzes which commands succeeded to determine which variants
        to use for subsequent files. This tests actual command behavior
        rather than OS type, since GNU utilities can be installed on
        BSD systems and vice versa.

        :param dict results: Command results from first file
        :param str path: The path that was used for detection
        :returns dict[str, Any]: Platform capabilities dictionary
        """
        platform: dict[str, Any] = {
            "stat_variant": None,
            "has_lsattr": False,
            "has_getfacl": False,
            "has_nfs4_getfacl": False,
            "has_getfattr": False,
            "has_xattr": False,
            "ls_supports_selinux": False,
            "ls_supports_acl_macos": False,
            "ls_supports_flags_bsd": False,
            "has_md5sum": False,
            "has_md5_bsd": False,
            "has_sha1sum": False,
            "has_sha256sum": False,
            "has_sha512sum": False,
            "has_shasum": False,
            "has_sha1_bsd": False,
            "has_sha256_bsd": False,
            "has_sha512_bsd": False,
        }

        # Detect stat variant - prefer GNU if both work (more features)
        # Note: Some BSD systems return rc=0 even for invalid options,
        # so we must also verify stdout contains expected numeric output.
        inode_gnu = results.get(f"{path}_inode", {})
        inode_bsd = results.get(f"{path}_inode_bsd", {})

        gnu_stdout = inode_gnu.get("stdout", "").strip()
        bsd_stdout = inode_bsd.get("stdout", "").strip()

        if inode_gnu.get("rc") == 0 and gnu_stdout.isdigit():
            platform["stat_variant"] = "gnu"
        elif inode_bsd.get("rc") == 0 and bsd_stdout.isdigit():
            platform["stat_variant"] = "bsd"

        # Check for lsattr (Linux ext2/3/4 attributes)
        flags_result = results.get(f"{path}_flags", {})
        if flags_result.get("rc") == 0 and flags_result.get("stdout", ""):
            platform["has_lsattr"] = True

        # Check for ls -ldO (BSD/macOS flags)
        flags_bsd_result = results.get(f"{path}_flags_macos", {})
        if flags_bsd_result.get("rc") == 0:
            platform["ls_supports_flags_bsd"] = True

        # Check for getfacl (Linux POSIX ACLs)
        acl_result = results.get(f"{path}_acl", {})
        if acl_result.get("rc") == 0 and acl_result.get("stdout", ""):
            platform["has_getfacl"] = True

        # Check for nfs4_getfacl (NFS v4 ACLs)
        acl_nfs4_result = results.get(f"{path}_acl_nfs4", {})
        if acl_nfs4_result.get("rc") == 0 and acl_nfs4_result.get(
            "stdout", ""
        ):
            platform["has_nfs4_getfacl"] = True

        # Check for ls -le (macOS ACLs)
        acl_macos_result = results.get(f"{path}_acl_macos", {})
        if acl_macos_result.get("rc") == 0:
            platform["ls_supports_acl_macos"] = True

        # Check for getfattr (Linux extended attributes)
        xattr_result = results.get(f"{path}_xattr", {})
        if xattr_result.get("rc") == 0:
            platform["has_getfattr"] = True

        # Check for xattr (macOS extended attributes)
        xattr_macos_result = results.get(f"{path}_xattr_macos", {})
        if xattr_macos_result.get("rc") == 0:
            platform["has_xattr"] = True

        # Check for SELinux support via ls -Z
        # On non-SELinux systems, ls -Z might succeed but show '?'
        selinux_ls_result = results.get(f"{path}_selinux_ls", {})
        if selinux_ls_result.get("rc") == 0:
            stdout = selinux_ls_result.get("stdout", "")
            # Check that output doesn't start with '?' (no SELinux)
            if stdout and not stdout.strip().startswith("?"):
                platform["ls_supports_selinux"] = True

        # Check for hash tools
        md5_result = results.get(f"{path}_md5", {})
        if md5_result.get("rc") == 0 and md5_result.get("stdout", ""):
            platform["has_md5sum"] = True

        md5_bsd_result = results.get(f"{path}_md5_bsd", {})
        if md5_bsd_result.get("rc") == 0 and md5_bsd_result.get("stdout", ""):
            platform["has_md5_bsd"] = True

        sha1_result = results.get(f"{path}_sha1", {})
        if sha1_result.get("rc") == 0 and sha1_result.get("stdout", ""):
            platform["has_sha1sum"] = True

        sha256_result = results.get(f"{path}_sha256", {})
        if sha256_result.get("rc") == 0 and sha256_result.get("stdout", ""):
            platform["has_sha256sum"] = True

        sha512_result = results.get(f"{path}_sha512", {})
        if sha512_result.get("rc") == 0 and sha512_result.get("stdout", ""):
            platform["has_sha512sum"] = True

        # Check for shasum (macOS)
        sha1_shasum_result = results.get(f"{path}_sha1_shasum", {})
        sha256_shasum_result = results.get(f"{path}_sha256_shasum", {})
        sha512_shasum_result = results.get(f"{path}_sha512_shasum", {})
        if (
            (
                sha1_shasum_result.get("rc") == 0
                and sha1_shasum_result.get("stdout", "")
            )
            or (
                sha256_shasum_result.get("rc") == 0
                and sha256_shasum_result.get("stdout", "")
            )
            or (
                sha512_shasum_result.get("rc") == 0
                and sha512_shasum_result.get("stdout", "")
            )
        ):
            platform["has_shasum"] = True

        # Check for BSD native SHA commands (OpenBSD, etc.)
        sha1_bsd_result = results.get(f"{path}_sha1_bsd", {})
        if sha1_bsd_result.get("rc") == 0 and sha1_bsd_result.get(
            "stdout", ""
        ):
            platform["has_sha1_bsd"] = True

        sha256_bsd_result = results.get(f"{path}_sha256_bsd", {})
        if sha256_bsd_result.get("rc") == 0 and sha256_bsd_result.get(
            "stdout", ""
        ):
            platform["has_sha256_bsd"] = True

        sha512_bsd_result = results.get(f"{path}_sha512_bsd", {})
        if sha512_bsd_result.get("rc") == 0 and sha512_bsd_result.get(
            "stdout", ""
        ):
            platform["has_sha512_bsd"] = True

        return platform

    def _parse_encoding_from_desc(self, desc: str) -> Optional[str]:
        """
        Parse encoding from file -b descriptive output.

        On systems like OpenBSD where --mime-encoding is not available,
        file -b returns descriptive text like "ASCII text",
        "ISO-8859 text", "Non-ISO extended-ASCII text", etc.

        :param str desc: Output from file -b command
        :returns Optional[str]: Detected encoding or None if binary/unknown
        """
        desc_lower = desc.lower()

        # Check if it's binary (no text-based encoding)
        if "text" not in desc_lower:
            return "binary"

        # Map common file descriptions to encoding names
        if "ascii" in desc_lower and "non-iso" not in desc_lower:
            return "us-ascii"
        elif "iso-8859" in desc_lower or "iso 8859" in desc_lower:
            # ISO-8859 text usually means ISO-8859-1 (Latin-1)
            return "iso-8859-1"
        elif "utf-8" in desc_lower or "utf8" in desc_lower:
            return "utf-8"
        elif "utf-16" in desc_lower or "utf16" in desc_lower:
            return "utf-16"
        elif "non-iso" in desc_lower and "extended-ascii" in desc_lower:
            # OpenBSD reports UTF-8 as "Non-ISO extended-ASCII text"
            return "utf-8"
        elif "text" in desc_lower:
            # Default to UTF-8 for any text file we can't identify
            return "utf-8"

        # Unknown or binary
        return None

    def _add_content_with_encoding(
        self,
        attributes: dict[str, Any],
        raw_content: str,
        encoding: str,
        path: str,
        options: dict[str, Any],
        forced: bool = False,
    ) -> None:
        """
        Add content to attributes with specified encoding.

        Handles special encodings (hex, base64) and text encodings.
        Falls back to base64 if auto-detected encoding fails.
        Fails if text decode fails with forced encoding.

        :param dict attributes: Metadata dict to update
        :param str raw_content: Raw content from cat command
        :param str encoding: Encoding to use (forced or auto-detected)
        :param str path: File path (for error messages)
        :param dict options: Options dict with content/lines flags
        :param bool forced: True if encoding was user-specified, False
            if auto-detected
        """
        # Convert raw_content back to bytes
        # Ansible may have decoded it with surrogateescape
        try:
            content_bytes = raw_content.encode("utf-8", "surrogateescape")
        except (UnicodeEncodeError, UnicodeDecodeError) as e:
            raise RuntimeError(f"Failed to process content for {path}: {e}")

        encoding_lower = encoding.lower()
        want_content = options.get("content", False)
        want_lines = options.get("lines", False)

        # Fail if lines requested with non-text encoding
        if want_lines and encoding_lower in {
            "hex",
            "base64",
            "binary",
            "unknown",
        }:
            raise ValueError(
                f"Cannot split binary content into lines for {path}. "
                f"The 'lines' parameter requires text content, but "
                f"encoding is '{encoding}'. Remove lines=true or use "
                f"a text encoding."
            )

        # Handle special encodings (only valid with content, not lines)
        if encoding_lower == "hex":
            # Hexadecimal representation
            attributes["content"] = content_bytes.hex()
            attributes["encoding"] = "hex"
        elif encoding_lower == "base64":
            # Base64 representation (user forced or auto-detected binary)
            attributes["content"] = base64.b64encode(content_bytes).decode(
                "ascii"
            )
            attributes["encoding"] = "base64"
        elif encoding_lower in {"binary", "unknown"}:
            # Auto-detected binary: use base64
            attributes["content"] = base64.b64encode(content_bytes).decode(
                "ascii"
            )
            attributes["encoding"] = "base64"
        else:
            # Text encoding: try to decode with specified encoding
            try:
                decoded_content = content_bytes.decode(encoding)
                clean_content = decoded_content.replace("\r", "")
                attributes["encoding"] = encoding

                # Add content key if requested
                if want_content:
                    attributes["content"] = clean_content

                # Add lines key if requested
                if want_lines:
                    attributes["lines"] = clean_content.splitlines()

            except (UnicodeDecodeError, LookupError) as e:
                # LookupError: unknown encoding
                # UnicodeDecodeError: decode failed
                if forced:
                    # User specified this encoding - fail with error
                    raise RuntimeError(
                        f"Failed to decode content for {path} with "
                        f"forced encoding '{encoding}': {e}"
                    )
                else:
                    # Auto-detected encoding failed - fall back to base64
                    attributes["content"] = base64.b64encode(
                        content_bytes
                    ).decode("ascii")
                    attributes["encoding"] = "base64"
                    # Cannot provide lines for binary content
                    if want_lines:
                        raise ValueError(
                            f"Cannot split binary content into lines for "
                            f"{path}. Auto-detected encoding '{encoding}' "
                            f"failed to decode, falling back to base64. "
                            f"Remove lines=true or specify a text encoding."
                        )

    def _process_read_results(
        self,
        results: dict[str, Any],
        paths: list[str],
        options: Optional[dict[str, Any]] = None,
    ) -> dict[str, Optional[dict[str, Any]]]:
        """
        Process raw command results into structured file data.

        Parses ls -din output using jc and extracts file attributes.

        :param dict results: Raw command results from _run()
        :param list[str] paths: Original paths that were inspected
        :param Optional[dict[str, bool]] options: Boolean options dict
            (attributes, extended, content, md5, sha1, sha256, sha512)
        :returns dict: Dictionary mapping paths to parsed file data or
            None if path doesn't exist
        """
        options = options or {"attributes": True}
        file_data: dict[str, Optional[dict[str, Any]]] = {}

        for path in paths:
            ls_key = f"{path}_ls"
            if ls_key not in results:
                file_data[path] = None
                continue

            ls_result = results[ls_key]

            # Path doesn't exist if ls failed
            if ls_result.get("rc") != 0:
                file_data[path] = None
                continue

            # Parse ls output using jc
            ls_output = ls_result.get("stdout", "")
            try:
                parsed = jc_parse("ls", ls_output)
                if not parsed or not isinstance(parsed, list):
                    file_data[path] = None
                    continue

                # ls returns a list, get first entry
                entry = parsed[0] if parsed else {}

                # Extract basic attributes
                attributes = {}
                include_attributes = options.get("attributes", False)

                # Extract file type from first char of flags
                # (always needed for content/extended logic)
                flags = entry.get("flags", "")
                if flags:
                    type_char = flags[0]
                    type_map = {
                        "-": "regular",
                        "d": "directory",
                        "l": "link",
                        "p": "pipe",
                        "s": "socket",
                        "c": "character",
                        "b": "block",
                    }
                    file_type = type_map.get(type_char, "unknown")
                    # Only add type if attributes requested
                    if include_attributes:
                        attributes["type"] = file_type
                else:
                    file_type = "unknown"

                # Add optional attributes fields only if requested
                if include_attributes:
                    # Extract octal mode from flags
                    if flags:
                        attributes["mode"] = flags_to_octal_mode(flags)

                    # Add other fields from ls output
                    # Only include size for regular files
                    if "size" in entry and file_type == "regular":
                        size_bytes = entry["size"]
                        # Format size with bytes and pretty keys
                        size_str = f"{size_bytes}B"
                        attributes["size"] = parse_si(
                            size_str, binary=True, optimize=True
                        )
                    if "owner" in entry:
                        attributes["owner"] = entry["owner"]
                    if "group" in entry:
                        attributes["group"] = entry["group"]

                    # Calculate permission flags
                    if flags and len(flags) >= 10:
                        perms = self._stat_permission_booleans(flags)
                        attributes["readable"] = perms.get("readable", False)
                        attributes["writable"] = perms.get("writeable", False)
                        attributes["executable"] = perms.get(
                            "executable", False
                        )

                # Add content/hardlinks field based on file type
                if file_type == "link" and include_attributes:
                    # For symlinks, target is the link target
                    # jc returns link_to field for symlink targets
                    if "link_to" in entry:
                        attributes["target"] = entry["link_to"]
                    else:
                        attributes["target"] = ""
                elif file_type == "regular" and include_attributes:
                    # For regular files, hardlinks is the count of OTHER links
                    # (raw count - 1), omit if zero
                    has_hardlinks = False
                    if "links" in entry:
                        other_links = entry["links"] - 1
                        if other_links > 0:
                            has_hardlinks = True
                            attributes["hardlinks"] = other_links

                    # Determine if inode should be included
                    # User can explicitly set inode=true/false
                    # Default: true if hardlinks exist, false otherwise
                    want_inode = options.get("inode")
                    if want_inode is None:
                        # Smart default: include if has hardlinks
                        include_inode = has_hardlinks
                    else:
                        # User explicitly set it
                        include_inode = want_inode

                    if include_inode:
                        # Get inode from stat for hardlink identification
                        inode_key = f"{path}_inode"
                        inode_bsd_key = f"{path}_inode_bsd"
                        if inode_key in results or inode_bsd_key in results:
                            # Try GNU stat first
                            inode_result = results.get(inode_key, {})
                            if inode_result.get("rc") != 0:
                                # Fall back to BSD stat
                                inode_result = results.get(inode_bsd_key, {})

                            if inode_result.get("rc") == 0:
                                inode_str = inode_result.get(
                                    "stdout", ""
                                ).strip()
                                try:
                                    attributes["inode"] = int(inode_str)
                                except (ValueError, TypeError):
                                    pass

                # Add content and encoding if requested and available
                if file_type == "regular":
                    cat_key = f"{path}_cat"
                    forced_encoding = options.get("encoding")

                    # Check if content reading was requested
                    if cat_key in results:
                        cat_result = results[cat_key]
                        if cat_result.get("rc") != 0:
                            # cat command failed
                            if forced_encoding or options.get("content"):
                                raise IOError(
                                    f"Failed to read content for {path}: "
                                    f"cat command failed"
                                )
                            # Skip if content not explicitly requested
                            continue

                        raw_content = cat_result.get("stdout", "")

                        # Determine encoding (forced or auto-detected)
                        if forced_encoding:
                            # User specified encoding - use it
                            encoding = forced_encoding
                        else:
                            # Auto-detect encoding
                            encoding_key = f"{path}_encoding"
                            encoding_bsd_key = f"{path}_encoding_bsd"
                            encoding_desc_key = f"{path}_encoding_desc"

                            # Check if auto-detection was requested
                            if not (
                                encoding_key in results
                                or encoding_bsd_key in results
                                or encoding_desc_key in results
                            ):
                                # No content requested for this path
                                continue

                            encoding_result = results.get(encoding_key, {})
                            encoding = None

                            # Try GNU file first (--mime-encoding)
                            if encoding_result.get("rc") == 0:
                                encoding = encoding_result.get(
                                    "stdout", ""
                                ).strip()
                            else:
                                # Fall back to BSD file -I
                                encoding_result = results.get(
                                    encoding_bsd_key, {}
                                )
                                if encoding_result.get("rc") == 0:
                                    # Parse BSD: "text/plain; charset=us-ascii"
                                    bsd_output = encoding_result.get(
                                        "stdout", ""
                                    ).strip()
                                    if "charset=" in bsd_output:
                                        # Extract charset value
                                        charset_part = bsd_output.split(
                                            "charset=", 1
                                        )[1]
                                        encoding = charset_part.split(";")[
                                            0
                                        ].strip()
                                else:
                                    # Fall back to OpenBSD file -b
                                    desc_result = results.get(
                                        encoding_desc_key, {}
                                    )
                                    if desc_result.get("rc") == 0:
                                        desc_output = desc_result.get(
                                            "stdout", ""
                                        ).strip()
                                        encoding = (
                                            self._parse_encoding_from_desc(
                                                desc_output
                                            )
                                        )

                            if not encoding:
                                raise RuntimeError(
                                    f"Content requested for {path} but "
                                    f"encoding detection failed. Ensure the "
                                    f"file command is installed."
                                )

                        # Process content with determined encoding
                        self._add_content_with_encoding(
                            attributes,
                            raw_content,
                            encoding,
                            path,
                            options,
                            forced=bool(forced_encoding),
                        )

                    # Add MIME type if requested
                    mimetype_key = f"{path}_mimetype"
                    mimetype_bsd_key = f"{path}_mimetype_bsd"
                    if mimetype_key in results or mimetype_bsd_key in results:
                        mimetype_result = results.get(mimetype_key, {})
                        mimetype = None

                        # Try GNU file first
                        if mimetype_result.get("rc") == 0:
                            mimetype = mimetype_result.get(
                                "stdout", ""
                            ).strip()
                        else:
                            # Fall back to BSD file -I
                            mimetype_result = results.get(mimetype_bsd_key, {})
                            if mimetype_result.get("rc") == 0:
                                # Parse BSD: "text/plain; charset=us-ascii"
                                bsd_output = mimetype_result.get(
                                    "stdout", ""
                                ).strip()
                                # Extract MIME type (before semicolon)
                                if ";" in bsd_output:
                                    mimetype = bsd_output.split(";")[0].strip()
                                else:
                                    mimetype = bsd_output

                        if not mimetype or "/" not in mimetype:
                            # MIME type was requested but failed
                            raise RuntimeError(
                                f"MIME type detection requested for {path} "
                                f"but file command failed. Ensure the file "
                                f"command is installed and accessible."
                            )

                        # Split into type and subtype
                        mime_parts = mimetype.split("/", 1)
                        attributes["mime"] = {
                            "type": mime_parts[0],
                            "subtype": mime_parts[1],
                        }

                # Add timestamps if requested
                stat_key = f"{path}_stat"
                stat_bsd_key = f"{path}_stat_bsd"
                if stat_key in results or stat_bsd_key in results:
                    # Try GNU stat first
                    stat_result = results.get(stat_key, {})
                    if stat_result.get("rc") != 0:
                        # Fall back to BSD stat
                        stat_result = results.get(stat_bsd_key, {})

                    if stat_result.get("rc") == 0:
                        stat_output = stat_result.get("stdout", "").strip()
                        times = stat_output.split()
                        if len(times) >= 3:
                            # busybox stat echoes format specifiers it
                            # does not know (%W comes back as W), so a
                            # non-numeric field means the filesystem or
                            # tool cannot answer and the timestamp is
                            # omitted
                            def _epoch_or_none(value: str) -> Optional[int]:
                                try:
                                    parsed_epoch = int(value)
                                except ValueError:
                                    return None
                                return parsed_epoch or None

                            mtime = _epoch_or_none(times[0])
                            ctime = _epoch_or_none(times[1])
                            btime = _epoch_or_none(times[2])

                            if mtime:
                                attributes["modified"] = (
                                    format_epoch_timestamp(mtime)
                                )
                            if ctime:
                                attributes["changed"] = format_epoch_timestamp(
                                    ctime
                                )
                            if btime:
                                attributes["created"] = format_epoch_timestamp(
                                    btime
                                )

                # Add ACL if requested
                acl_key = f"{path}_acl"
                acl_nfs4_key = f"{path}_acl_nfs4"
                acl_macos_key = f"{path}_acl_macos"
                if (
                    acl_key in results
                    or acl_nfs4_key in results
                    or acl_macos_key in results
                ):
                    # Try ACL commands in order: POSIX, NFS v4, macOS
                    acl_result = results.get(acl_key, {})
                    acl_type = "posix"

                    if acl_result.get("rc") != 0:
                        # Fall back to NFS v4
                        acl_result = results.get(acl_nfs4_key, {})
                        acl_type = "nfs4"

                    if acl_result.get("rc") != 0:
                        # Fall back to macOS ls -le
                        acl_result = results.get(acl_macos_key, {})
                        acl_type = "macos"

                    if acl_result.get("rc") == 0:
                        # Command succeeded - parse ACL
                        acl_text = acl_result.get("stdout", "").strip()
                        if acl_text:
                            if acl_type == "macos":
                                macos_acl = self._parse_macos_acl(acl_text)
                                # ls marks a path carrying an ACL with a
                                # trailing + on its mode string, so an
                                # empty parse means entries were lost
                                mode = entry.get("flags", "")
                                acl_entries = (macos_acl or {}).get("entries")
                                if mode.endswith("+") and not acl_entries:
                                    raise ValueError(
                                        f"Mode {mode} advertises an ACL "
                                        f"for {path} but no ACL entries "
                                        f"were parsed from: {acl_text!r}"
                                    )
                                attributes["acl"] = macos_acl
                            elif acl_type == "nfs4":
                                attributes["acl"] = self._parse_nfs4_acl(
                                    acl_text
                                )
                            else:
                                attributes["acl"] = self._parse_posix_acl(
                                    acl_text
                                )
                    else:
                        # All commands failed - system doesn't support ACLs
                        attributes["acl"] = {}

                # Add extended attributes if requested
                xattr_key = f"{path}_xattr"
                xattr_macos_key = f"{path}_xattr_macos"
                if xattr_key in results or xattr_macos_key in results:
                    # Try getfattr first (Linux)
                    xattr_result = results.get(xattr_key, {})
                    xattr_type = "linux"
                    if xattr_result.get("rc") != 0:
                        # Fall back to macOS xattr
                        xattr_result = results.get(xattr_macos_key, {})
                        xattr_type = "macos"

                    if xattr_result.get("rc") == 0:
                        xattr_text = xattr_result.get("stdout", "").strip()
                        if xattr_text:
                            xattr_parsed = self._process_xattrs(
                                xattr_text, xattr_type=xattr_type
                            )
                            # Add xattrs if any were found
                            if xattr_parsed.get("xattrs"):
                                attributes["xattrs"] = xattr_parsed["xattrs"]
                            # Merge SELinux from xattrs if not already set
                            if (
                                "selinux" in xattr_parsed
                                and "selinux" not in attributes
                            ):
                                attributes["selinux"] = xattr_parsed["selinux"]

                            # Check for ACL xattrs when ACL commands failed
                            # Only POSIX ACLs use xattrs (macOS/APFS stores
                            # ACLs in filesystem attributes)
                            if attributes.get("acl") == {}:
                                xattrs = xattr_parsed.get("xattrs", {})
                                acl_xattrs = [
                                    "system.posix_acl_access",
                                    "system.posix_acl_default",
                                ]
                                found_acl_xattrs = [
                                    x for x in acl_xattrs if x in xattrs
                                ]
                                if found_acl_xattrs:
                                    # Set type to indicate POSIX ACLs present
                                    # even though we couldn't read them
                                    attributes["acl"] = {"type": "posix"}
                                    xattr_list = ", ".join(found_acl_xattrs)
                                    self._display.warning(
                                        f"[{self.inventory_hostname}] "
                                        f"Found POSIX ACL extended "
                                        f"attributes ({xattr_list}) but "
                                        f"getfacl command failed for {path}. "
                                        f"ACL tools may be missing or "
                                        f"inaccessible."
                                    )

                # Add filesystem flags if requested
                flags_key = f"{path}_flags"
                flags_macos_key = f"{path}_flags_macos"
                if flags_key in results or flags_macos_key in results:
                    # Try lsattr first (Linux)
                    flags_result = results.get(flags_key, {})
                    if flags_result.get("rc") == 0:
                        flags_output = flags_result.get("stdout", "")
                        flags = self._process_linux_flags(flags_output)
                        attributes["flags"] = flags
                    else:
                        # Fall back to macOS ls -ldO
                        flags_result = results.get(flags_macos_key, {})
                        if flags_result.get("rc") == 0:
                            flags_output = flags_result.get("stdout", "")
                            flags = self._process_macos_flags(flags_output)
                            attributes["flags"] = flags
                        else:
                            # Neither command succeeded, set empty default
                            attributes["flags"] = []

                # Add SELinux context if requested
                selinux_key = f"{path}_selinux"
                selinux_ls_key = f"{path}_selinux_ls"
                if selinux_key in results or selinux_ls_key in results:
                    # Try stat -c %C first
                    selinux_result = results.get(selinux_key, {})
                    if selinux_result.get("rc") != 0:
                        # Fall back to ls -Zd
                        selinux_result = results.get(selinux_ls_key, {})

                    if selinux_result.get("rc") == 0:
                        selinux_text = selinux_result.get("stdout", "").strip()
                        if selinux_text and not selinux_text.startswith("?"):
                            attributes["selinux"] = selinux_text

                # Add directory children if this is a directory and
                # ls command was run (either for children parameter or
                # explicitly requested via include)
                if attributes.get("type") == "directory":
                    contents_key = f"{path}_contents"
                    if contents_key in results:
                        contents_result = results.get(contents_key, {})
                        if contents_result.get("rc") == 0:
                            contents_output = contents_result.get(
                                "stdout", ""
                            ).strip()
                            if contents_output:
                                # Split by newlines and create full paths
                                filenames = contents_output.split("\n")
                                attributes["children"] = [
                                    join(path, filename)
                                    for filename in filenames
                                    if filename
                                ]
                            else:
                                # Empty directory
                                attributes["children"] = []
                        else:
                            # Could not list directory (e.g., no permission)
                            attributes["children"] = []

                # Add hash checksums if requested
                # Only process for regular files
                if attributes.get("type") == "regular":
                    # MD5 - try GNU md5sum first, then BSD md5
                    if (
                        f"{path}_md5" in results
                        or f"{path}_md5_bsd" in results
                    ):
                        md5_result = results.get(f"{path}_md5", {})
                        if md5_result.get("rc") != 0:
                            md5_result = results.get(f"{path}_md5_bsd", {})
                        if md5_result.get("rc") == 0:
                            md5_output = md5_result.get("stdout", "").strip()
                            # Parse hash: GNU format is "hash filename",
                            # BSD format is just "hash"
                            md5_hash = md5_output.split()[0]
                            if md5_hash:
                                attributes["md5"] = md5_hash
                        else:
                            # MD5 was requested but failed
                            raise RuntimeError(
                                f"MD5 checksum requested for {path} but "
                                f"all hash commands failed. Ensure md5sum "
                                f"or md5 is installed."
                            )

                    # SHA-1 - try GNU, shasum, then BSD native
                    if (
                        f"{path}_sha1" in results
                        or f"{path}_sha1_shasum" in results
                        or f"{path}_sha1_bsd" in results
                    ):
                        sha1_result = results.get(f"{path}_sha1", {})
                        if sha1_result.get("rc") != 0:
                            sha1_result = results.get(
                                f"{path}_sha1_shasum", {}
                            )
                        if sha1_result.get("rc") != 0:
                            sha1_result = results.get(f"{path}_sha1_bsd", {})
                        if sha1_result.get("rc") == 0:
                            sha1_output = sha1_result.get("stdout", "").strip()
                            sha1_hash = sha1_output.split()[0]
                            if sha1_hash:
                                attributes["sha1"] = sha1_hash
                        else:
                            # SHA-1 was requested but failed
                            raise RuntimeError(
                                f"SHA-1 checksum requested for {path} but "
                                f"all hash commands failed. Ensure sha1sum, "
                                f"shasum, or sha1 is installed."
                            )

                    # SHA-256 - try GNU, shasum, then BSD native
                    if (
                        f"{path}_sha256" in results
                        or f"{path}_sha256_shasum" in results
                        or f"{path}_sha256_bsd" in results
                    ):
                        sha256_result = results.get(f"{path}_sha256", {})
                        if sha256_result.get("rc") != 0:
                            sha256_result = results.get(
                                f"{path}_sha256_shasum", {}
                            )
                        if sha256_result.get("rc") != 0:
                            sha256_result = results.get(
                                f"{path}_sha256_bsd", {}
                            )
                        if sha256_result.get("rc") == 0:
                            sha256_output = sha256_result.get(
                                "stdout", ""
                            ).strip()
                            sha256_hash = sha256_output.split()[0]
                            if sha256_hash:
                                attributes["sha256"] = sha256_hash
                        else:
                            # SHA-256 was requested but failed
                            raise RuntimeError(
                                f"SHA-256 checksum requested for {path} "
                                f"but all hash commands failed. Ensure "
                                f"sha256sum, shasum, or sha256 is installed."
                            )

                    # SHA-512 - try GNU, shasum, then BSD native
                    if (
                        f"{path}_sha512" in results
                        or f"{path}_sha512_shasum" in results
                        or f"{path}_sha512_bsd" in results
                    ):
                        sha512_result = results.get(f"{path}_sha512", {})
                        if sha512_result.get("rc") != 0:
                            sha512_result = results.get(
                                f"{path}_sha512_shasum", {}
                            )
                        if sha512_result.get("rc") != 0:
                            sha512_result = results.get(
                                f"{path}_sha512_bsd", {}
                            )
                        if sha512_result.get("rc") == 0:
                            sha512_output = sha512_result.get(
                                "stdout", ""
                            ).strip()
                            sha512_hash = sha512_output.split()[0]
                            if sha512_hash:
                                attributes["sha512"] = sha512_hash
                        else:
                            # SHA-512 was requested but failed
                            raise RuntimeError(
                                f"SHA-512 checksum requested for {path} "
                                f"but all hash commands failed. Ensure "
                                f"sha512sum, shasum, or sha512 is installed."
                            )

                file_data[path] = attributes

            except Exception as e:
                raise ValueError(
                    f"Failed to parse file attributes for {path}: "
                    f"{type(e).__name__}: {e}"
                ) from e

        return file_data

    def _stat_permission_booleans(self, flags: str) -> dict[str, bool]:
        """Parse permission booleans from flags string.

        :param str flags: Permission flags string (e.g., "-rw-r--r--")
        :returns dict[str, bool]: Permission boolean dictionary
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

    def _parse_macos_acl(self, acl_text: str) -> Optional[dict[str, Any]]:
        """Parse macOS ACL output from ls -le into simplified dict.

        Format: ``0: group:everyone deny write``

        An entry inherited from a parent directory carries an
        ``inherited`` token between the name and the allow/deny word,
        as in ``0: group:staff inherited allow read``. Such entries
        set ``inherited`` to true; the key is absent on direct entries.

        Returns simplified structure where each entry has type and name
        fields, with rights represented as boolean fields. Deny sets
        false, allow sets true. Only explicitly mentioned rights are
        included.

        A line that opens like an ACE but does not match the entry
        format raises rather than being dropped, since a discarded
        entry would misreport the permissions in force. Lines that do
        not claim to be entries, such as the ls -l line above them,
        are still ignored.

        :param str acl_text: Raw ls -le output
        :returns Optional[dict[str, Any]]: Parsed ACL or None if no entries
        :raises ValueError: If a line claims to be an ACE but does not
                            parse
        """
        import re

        entries: list[dict[str, Any]] = []
        # Pattern: index: qualifier:name [inherited] permission rights
        pattern = re.compile(
            r"^\s*(\d+):\s+"  # index
            r"(\w+):(\S+)\s+"  # qualifier:name
            r"(?:(inherited)\s+)?"  # optional inherited marker
            r"(allow|deny)\s+"  # permission
            r"(.+)$"  # rights
        )
        # A leading index is ls claiming the line is an ACE
        ace_line = re.compile(r"^\s*\d+:")

        # Mapping of macOS ACL rights to schema fields
        # Note: macOS uses different names for files vs directories:
        #   files: read_data, write_data, execute, append_data
        #   directories: list/list_directory, add_file, search,
        #                add_subdirectory
        # We normalize these to common field names
        right_aliases = {
            "list": "read",
            "list_directory": "read",
            "read_data": "read",
            "add_file": "write",
            "write_data": "write",
            "search": "execute",
            "add_subdirectory": "append",
            "append_data": "append",
        }

        # Basic rights after normalization
        basic_rights = {
            "read",
            "write",
            "execute",
            "delete",
            "append",
            "delete_child",
            "chown",
        }

        # Nested field mappings: right_name -> (parent_key, field_name)
        attr_map = {
            "readattr": ("attributes", "read"),
            "writeattr": ("attributes", "write"),
        }

        ext_map = {
            "readextattr": ("extended", "read"),
            "writeextattr": ("extended", "write"),
        }

        sec_map = {
            "readsecurity": ("security", "read"),
            "writesecurity": ("security", "write"),
        }

        # Inheritance flags (stored under inheritance key)
        inherit_flags = {
            "file_inherit": "file",
            "directory_inherit": "directory",
            "limit_inherit": "limit",
            "only_inherit": "only",
        }

        for line in acl_text.splitlines():
            match = pattern.match(line)
            if match:
                index, qualifier, name, inherited, permission, rights_str = (
                    match.groups()
                )
                # Parse rights (comma or space separated)
                rights = [
                    r.strip()
                    for r in re.split(r"[,\s]+", rights_str)
                    if r.strip()
                ]

                # Build simplified entry
                entry: dict[str, Any] = {}

                # Set type and name fields
                entry["type"] = qualifier
                entry["name"] = name

                # Entries received from a parent directory are marked
                # ahead of the allow/deny word
                if inherited:
                    entry["inherited"] = True

                # Determine boolean value: allow=true, deny=false
                value = permission == "allow"

                # Track nested groups
                attributes: dict[str, bool] = {}
                extended: dict[str, bool] = {}
                security: dict[str, bool] = {}
                inheritance: dict[str, Any] = {}

                # Process each right
                for right in rights:
                    # Normalize right name using aliases
                    normalized_right = right_aliases.get(right, right)

                    if normalized_right in basic_rights:
                        entry[normalized_right] = value
                    elif right in attr_map:
                        parent_key, field_name = attr_map[right]
                        attributes[field_name] = value
                    elif right in ext_map:
                        parent_key, field_name = ext_map[right]
                        extended[field_name] = value
                    elif right in sec_map:
                        parent_key, field_name = sec_map[right]
                        security[field_name] = value
                    elif right in inherit_flags:
                        field_name = inherit_flags[right]
                        inheritance[field_name] = True

                # Add nested dicts only if they have content
                if attributes:
                    entry["attributes"] = attributes
                if extended:
                    entry["extended"] = extended
                if security:
                    entry["security"] = security
                if inheritance:
                    # Convert limit to propagate (inverse for readability)
                    # Only add propagate if there's actual inheritance
                    if "file" in inheritance or "directory" in inheritance:
                        has_limit = inheritance.pop("limit", False)
                        inheritance["propagate"] = not has_limit
                    entry["inheritance"] = inheritance

                entries.append(entry)

            elif ace_line.match(line):
                # Dropping an entry we cannot read would understate the
                # permissions in force, so refuse the whole ACL
                raise ValueError(f"Unparseable macOS ACL entry: {line!r}")

        # Always return the structure with type, even if no entries
        # Empty entries means file has no ACL (but system supports ACLs)
        return {"type": "macos", "entries": entries}

    def _parse_posix_acl(self, acl_text: str) -> Optional[dict[str, Any]]:
        """Parse POSIX ACL output from getfacl into simplified dict.

        Format::

            # file: path
            # owner: user
            # group: group
            user::rwx
            user:john:r-x
            group::r-x
            mask::r-x
            other::r-x

        Returns simplified structure where each entry has type and optional
        name fields. Only extended ACL entries (named users/groups, mask)
        are included - basic entries (owner, group_owner, other) are
        excluded as they represent standard Unix permissions.

        :param str acl_text: Raw getfacl output
        :returns dict[str, Any]: Parsed ACL structure (empty entries if
            only basic permissions)
        """
        extended_entries: list[dict[str, Any]] = []

        for line in acl_text.splitlines():
            line = line.strip()
            if not line:
                continue

            # Skip all comment lines (including attributes)
            if line.startswith("#"):
                continue

            # Parse ACL entry: type:name:perms or type::perms
            parts = line.split(":")
            if len(parts) >= 3:
                entry_type = parts[0]
                name = parts[1] if parts[1] else None
                perms = parts[2] if len(parts) > 2 else ""

                entry: dict[str, Any] = {}
                is_extended = False

                # Handle named vs non-named entries
                if name:
                    # Named user or group - EXTENDED ACL entry
                    entry["type"] = entry_type
                    entry["name"] = name
                    is_extended = True
                else:
                    # Non-named entries - check if extended or basic
                    if entry_type == "user":
                        # user:: is owner (basic, skip)
                        continue
                    elif entry_type == "group":
                        # group:: is group_owner (basic, skip)
                        continue
                    elif entry_type == "other":
                        # other:: is basic, skip
                        continue
                    elif entry_type == "mask":
                        # mask:: only exists with extended ACLs
                        entry["type"] = "mask"
                        is_extended = True
                    else:
                        # Other types (e.g., default:user::)
                        entry["type"] = entry_type
                        is_extended = True

                # Parse permissions to boolean fields (only for extended)
                if is_extended:
                    if "r" in perms:
                        entry["read"] = True
                    if "w" in perms:
                        entry["write"] = True
                    if "x" in perms:
                        entry["execute"] = True

                    extended_entries.append(entry)

        # Always return structure with type, even if no extended entries
        # Empty entries means file has only basic Unix permissions
        return {"type": "posix", "entries": extended_entries}

    def _parse_nfs4_acl(self, acl_text: str) -> dict[str, Any]:
        """Parse NFS v4 ACL output from nfs4_getfacl into simplified dict.

        Format: ``A::OWNER@:rwatTnNcCoy``

        TYPE:FLAGS:PRINCIPAL:PERMISSIONS
        - TYPE: A (allow), D (deny), U (audit), L (alarm)
        - FLAGS: f (file_inherit), d (directory_inherit), i (inherit_only),
                 n (no_propagate), I (inherited)
        - PRINCIPAL: OWNER@, GROUP@, EVERYONE@, or user@domain
        - PERMISSIONS: r,w,a,x,d,D,t,T,n,N,c,C,o,y (various rights)

        Returns simplified structure where each entry has type and optional
        name fields, with rights represented as boolean fields.

        :param str acl_text: Raw nfs4_getfacl output
        :returns dict[str, Any]: Parsed ACL structure
        """
        entries: list[dict[str, Any]] = []

        # Permission mapping: NFS v4 letter codes to our schema
        perm_map = {
            "r": "read",  # read_data / list_directory
            "w": "write",  # write_data / add_file
            "a": "append",  # append_data / add_subdirectory
            "x": "execute",
            "d": "delete",
            "D": "delete_child",
            "t": ("attributes", "read"),  # read_attributes
            "T": ("attributes", "write"),  # write_attributes
            "n": ("extended", "read"),  # read_named_attrs
            "N": ("extended", "write"),  # write_named_attrs
            "c": ("security", "read"),  # read_acl
            "C": ("security", "write"),  # write_acl
            "o": "chown",  # write_owner
            "y": "synchronize",
        }

        # Inheritance flags mapping
        inherit_flags_map = {
            "f": "file",  # file_inherit
            "d": "directory",  # directory_inherit
            "i": "only",  # inherit_only
            "n": "limit",  # no_propagate (will be converted to propagate)
            "I": "inherited",  # This ACE was inherited
        }

        for line in acl_text.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue

            # Parse NFS v4 ACE: TYPE:FLAGS:PRINCIPAL:PERMISSIONS
            parts = line.split(":")
            if len(parts) != 4:
                continue

            ace_type, flags_str, principal, perms_str = parts

            entry: dict[str, Any] = {}

            # Parse principal (user/group identification)
            if principal == "OWNER@":
                entry["type"] = "owner"
            elif principal == "GROUP@":
                entry["type"] = "group_owner"
            elif principal == "EVERYONE@":
                entry["type"] = "everyone"
            elif "@" in principal:
                # Named principal: user@domain or group@domain
                # NFS v4 doesn't distinguish user vs group in principal
                # format, but typically lowercase indicates user
                entry["type"] = "user"
                entry["name"] = principal
            else:
                # Fallback for non-standard principals
                entry["type"] = "user"
                entry["name"] = principal

            # Determine boolean value based on ACE type
            value = ace_type == "A"  # Allow=true, Deny=false

            # Track nested permission groups
            attributes: dict[str, bool] = {}
            extended: dict[str, bool] = {}
            security: dict[str, bool] = {}
            inheritance: dict[str, Any] = {}

            # Parse permissions
            for perm in perms_str:
                if perm in perm_map:
                    mapped = perm_map[perm]
                    if isinstance(mapped, tuple):
                        # Nested permission
                        parent_key, field_name = mapped
                        if parent_key == "attributes":
                            attributes[field_name] = value
                        elif parent_key == "extended":
                            extended[field_name] = value
                        elif parent_key == "security":
                            security[field_name] = value
                    else:
                        # Top-level permission
                        entry[mapped] = value

            # Parse inheritance flags
            for flag in flags_str:
                if flag in inherit_flags_map:
                    field_name = inherit_flags_map[flag]
                    if field_name == "inherited":
                        entry["inherited"] = True
                    else:
                        inheritance[field_name] = True

            # Add nested dicts only if they have content
            if attributes:
                entry["attributes"] = attributes
            if extended:
                entry["extended"] = extended
            if security:
                entry["security"] = security
            if inheritance:
                # Convert no_propagate (limit) to propagate for consistency
                if "file" in inheritance or "directory" in inheritance:
                    has_limit = inheritance.pop("limit", False)
                    inheritance["propagate"] = not has_limit
                entry["inheritance"] = inheritance

            entries.append(entry)

        # Always return structure with type, even if no entries
        return {"type": "nfs4", "entries": entries}

    def _is_binary_value(self, value: str) -> bool:
        """Check if a string value appears to be binary data.

        Considers a value binary if it contains non-printable characters
        (excluding common whitespace like tab, newline, carriage return).

        :param str value: The string value to check
        :returns bool: True if value contains binary/non-printable data
        """
        for char in value:
            code = ord(char)
            # Allow printable ASCII (32-126), tab, newline, carriage return
            if code < 32 and code not in (9, 10, 13):
                return True
            # Allow extended ASCII but flag surrogate escapes and control
            if 0x7F <= code < 0xA0:
                return True
            # Surrogate escape markers from Python's surrogateescape
            if 0xDC80 <= code <= 0xDCFF:
                return True
        return False

    def _encode_xattr_value(self, value: str) -> dict[str, str]:
        """Encode an xattr value with encoding and value fields.

        Returns a dict with 'encoding' (utf-8 or base64) and 'value'.

        :param str value: The xattr value to encode
        :returns dict[str, str]: Dict with encoding and value fields
        """
        if not self._is_binary_value(value):
            return {"encoding": "utf-8", "value": value}

        # Convert surrogates back to bytes and base64 encode
        try:
            raw_bytes = value.encode("utf-8", "surrogateescape")
            encoded = base64.b64encode(raw_bytes).decode("ascii")
            return {"encoding": "base64", "value": encoded}
        except (UnicodeEncodeError, UnicodeDecodeError):
            return {"encoding": "utf-8", "value": value}

    def _process_xattrs(
        self,
        source: Optional[str],
        xattr_type: str = "linux",
    ) -> dict[str, Any]:
        """Parse xattr output into nested dictionary structure.

        Parses getfattr (Linux) or xattr -l (macOS) output into a nested
        dictionary. Binary values are base64 encoded. ACL and SELinux
        xattrs are separated from regular xattrs.

        :param Optional[str] source: Raw xattr command output
        :param str xattr_type: Either 'linux' (getfattr) or 'macos' (xattr)
        :returns dict[str, Any]: Dictionary with keys:
            - 'xattrs': Nested dict of xattr values (may be empty dict).
              Text values are strings, binary values are
              ``{"_base64": "..."}``
            - 'selinux': SELinux context if found in xattrs (optional)
        """
        result: dict[str, Any] = {"xattrs": {}}

        if not source or not isinstance(source, str):
            return result

        flat_xattrs: dict[str, Any] = {}
        selinux_value: Optional[str] = None
        selinux_key = "security.selinux"

        def process_entry(key: str, value: str) -> None:
            nonlocal selinux_value
            key = key.strip()
            if not key:
                return

            lowered = key.lower()

            # Handle SELinux - extract to top level but also include in xattrs
            if lowered == selinux_key:
                if value and selinux_value is None:
                    # Remove null terminator if present
                    selinux_value = value.rstrip("\x00")
                # Continue to also add to xattrs (don't return)

            # All xattrs (including ACL) go into the nested structure
            encoded = self._encode_xattr_value(value)
            flat_xattrs[key] = encoded

        # Parse based on format
        if xattr_type == "linux":
            # getfattr format: key="value" or key=0xHEX
            for line in source.splitlines():
                stripped = line.strip()
                if not stripped or stripped.startswith("#"):
                    continue
                if "=" in stripped:
                    key, raw_val = stripped.split("=", 1)
                    # Remove quotes from value
                    val = raw_val.strip().strip('"').strip("'")
                    process_entry(key, val)
        else:
            # macOS xattr -lx format: "key:\n<hex dump>"
            # All values are hex dumps with -lx flag
            # Key line ends with ":" and next lines are hex dump
            lines = source.splitlines()
            i = 0
            while i < len(lines):
                line = lines[i]
                # Skip empty lines and hex dump lines (start with offset)
                if not line or line[0].isdigit() or line.startswith(" "):
                    i += 1
                    continue

                # Key line ends with ":"
                if line.endswith(":"):
                    key = line[:-1].strip()

                    # Collect hex dump lines that follow
                    hex_lines = []
                    j = i + 1
                    while j < len(lines):
                        hex_line = lines[j]
                        # Hex lines start with offset (8 hex digits)
                        if (
                            hex_line
                            and len(hex_line) > 8
                            and hex_line[:8].isalnum()
                        ):
                            # Check if it looks like hex offset
                            try:
                                int(hex_line[:8], 16)
                                hex_lines.append(hex_line)
                                j += 1
                                continue
                            except ValueError:
                                pass
                        break

                    if hex_lines:
                        # Parse hex dump to bytes
                        raw_bytes = self._parse_macos_hex_dump(hex_lines)
                        if raw_bytes:
                            # Try to decode as text, fall back to base64
                            try:
                                text = raw_bytes.decode("utf-8")
                                # Strip null terminator if present
                                flat_xattrs[key] = {
                                    "encoding": "utf-8",
                                    "value": text.rstrip("\x00"),
                                }
                            except UnicodeDecodeError:
                                encoded = base64.b64encode(raw_bytes)
                                flat_xattrs[key] = {
                                    "encoding": "base64",
                                    "value": encoded.decode("ascii"),
                                }
                        i = j
                        continue

                i += 1

        # Apply unflatten to create nested structure
        if flat_xattrs:
            # Use both . and : as separators for macOS compatibility
            nested = unflatten(flat_xattrs, separators=[".", ":"])
            result["xattrs"] = nested

        # Add SELinux if found (also included in xattrs for completeness)
        if selinux_value:
            result["selinux"] = selinux_value

        return result

    def _parse_macos_hex_dump(self, hex_lines: list[str]) -> bytes:
        """Parse macOS xattr hex dump format into bytes.

        macOS xattr -l outputs binary data as hex dump with format:
        ``00000000  62 70 6C 69 ...  |bplist00...|``

        :param list[str] hex_lines: Lines from hex dump
        :returns bytes: Decoded binary data
        """
        result = bytearray()
        for line in hex_lines:
            # Format: offset  HH HH HH ...  |ASCII|
            line = line.strip()
            if not line:
                continue

            # Split on multiple spaces to separate offset, hex, ascii
            parts = line.split("  ")
            if len(parts) < 2:
                continue

            # Extract hex portion (between offset and ASCII)
            hex_part = parts[1] if len(parts) >= 2 else ""
            # Handle case where there's more hex in parts[2]
            if len(parts) >= 3 and not parts[2].startswith("|"):
                hex_part += " " + parts[2]

            # Parse hex bytes
            for byte_str in hex_part.split():
                if len(byte_str) == 2:
                    try:
                        result.append(int(byte_str, 16))
                    except ValueError:
                        pass

        return bytes(result)

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

    def _process_linux_flags(self, flags_output: str) -> list[str]:
        """Process Linux lsattr output into attributes list.

        :param str flags_output: Raw lsattr output
        :returns list[str]: List of attribute names
        """
        flags_text = flags_output.strip()
        parts = flags_text.split()
        if not parts:
            return []

        raw_flags = parts[0]
        attributes = self._normalize_flags(raw_flags)
        return attributes

    def _process_macos_flags(self, flags_output: str) -> list[str]:
        """Process macOS ls -ldO output into attributes list.

        :param str flags_output: Raw ls -ldO output
        :returns list[str]: List of attribute names
        """
        flags_text = flags_output.strip()
        parts = flags_text.split()
        if len(parts) < 5:
            return []

        flag_str = parts[4]
        if flag_str == "-":
            return []

        # macOS uses comma-separated or space-separated flags
        attributes = self._normalize_flags(flag_str)
        return attributes
