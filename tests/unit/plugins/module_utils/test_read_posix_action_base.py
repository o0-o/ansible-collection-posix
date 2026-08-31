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

"""Unit tests for ReadPosixActionBase command planning helpers."""

from __future__ import annotations

from typing import Any, Optional
from unittest.mock import MagicMock

import pytest

try:
    from ansible_collections.o0_o.posix.plugins.module_utils.read_posix_action_base import (  # type: ignore  # noqa: E501
        RESOLUTION_END_MARKER,
        RESOLUTION_MAX_HOPS,
        ReadPosixActionBase,
    )
except ModuleNotFoundError:  # pragma: no cover - ansible missing in tests
    ReadPosixActionBase = None  # type: ignore
    RESOLUTION_END_MARKER = "@RESOLVED@"  # type: ignore
    RESOLUTION_MAX_HOPS = 40  # type: ignore

pytestmark = pytest.mark.skipif(
    ReadPosixActionBase is None, reason="ansible package is required"
)


class DummyReadAction(ReadPosixActionBase):
    """Minimal ReadPosixActionBase subclass with no Ansible plumbing."""

    def __init__(self) -> None:
        self.inventory_hostname = "testhost"
        self._display = MagicMock()


class BatchingReadAction(DummyReadAction):
    """DummyReadAction recording the command batches it is asked to run.

    Overriding _run_action on the class rather than the instance keeps
    the stub honest: its signature must keep matching production's.
    """

    def __init__(self, commands: Optional[dict[str, Any]] = None) -> None:
        super().__init__()
        self.batches: list[dict[str, Any]] = []
        self.reply = {
            "commands": commands if commands is not None else {},
            "count": 4,
            "batches": 1,
        }

    def _run_action(
        self,
        plugin_name: str,
        plugin_args: dict[str, Any],
        task_vars: Optional[dict[str, Any]] = None,
        check_mode: Optional[bool] = None,
    ) -> dict[str, Any]:
        """Record the batch and answer with a canned run result."""
        self.batches.append(plugin_args["commands"])
        return self.reply


def _ls_result(flags: str, path: str = "/f") -> dict[str, Any]:
    """Build an ls -dn result whose flags carry the wanted file type."""
    return {
        "rc": 0,
        "stdout": f"{flags}  1  0  0  0 Aug 16 10:00 {path}",
    }


def _ls_link_result(path: str, target: str) -> dict[str, Any]:
    """Build an ls -dn result for a symlink naming its target."""
    return {
        "rc": 0,
        "stdout": f"lrwxrwxrwx  1  0  0  0 Aug 16 10:00 {path} -> {target}",
    }


@pytest.fixture
def action() -> DummyReadAction:
    """Provide a bare ReadPosixActionBase instance per test."""
    return DummyReadAction()


class TestStatPermissionBooleans:
    """Tests for _stat_permission_booleans."""

    def test_regular_file_permissions(self, action) -> None:
        """Test every boolean derived from a plain 0644 mode string."""
        assert action._stat_permission_booleans("-rw-r--r--") == {
            "rusr": True,
            "wusr": True,
            "xusr": False,
            "rgrp": True,
            "wgrp": False,
            "xgrp": False,
            "roth": True,
            "woth": False,
            "xoth": False,
            "isuid": False,
            "isgid": False,
        }

    def test_setuid_setgid_and_sticky_bits(self, action) -> None:
        """Test lowercase s and t set both execute and special bits."""
        assert action._stat_permission_booleans("-rwsr-sr-t") == {
            "rusr": True,
            "wusr": True,
            "xusr": True,
            "rgrp": True,
            "wgrp": False,
            "xgrp": True,
            "roth": True,
            "woth": False,
            "xoth": True,
            "isuid": True,
            "isgid": True,
        }

    @pytest.mark.parametrize(
        "flags,key,expected",
        [
            ("-rwSr--r--", "isuid", True),
            ("-rwSr--r--", "xusr", False),
            ("-rw-r-Sr--", "isgid", True),
            ("-rw-r-Sr--", "xgrp", False),
            ("drwxr-xr-T", "xoth", False),
            ("drwxr-xr-t", "xoth", True),
        ],
    )
    def test_capitalized_special_bits(
        self, action, flags, key, expected
    ) -> None:
        """Test capital S and T set the bit but not execute."""
        assert action._stat_permission_booleans(flags)[key] is expected

    def test_trailing_acl_marker_is_ignored(self, action) -> None:
        """Test an ls ACL '+' suffix does not disturb the parse."""
        perms = action._stat_permission_booleans("drwxr-xr-x+")

        assert perms["rusr"] is True
        assert perms["xusr"] is True
        assert perms["woth"] is False

    def test_the_mode_settles_no_permission_of_its_own(self, action) -> None:
        """Test the triple is not derived from the bits.

        An ACL, a read-only mount and a MAC policy each make what a
        file's mode says differ from what the kernel will do, and root
        reads what the mode would refuse anybody, so the mode answers
        for itself and nothing else.
        """
        perms = action._stat_permission_booleans("-rw-r--r--")

        assert "readable" not in perms
        assert "writable" not in perms
        assert "executable" not in perms

    @pytest.mark.parametrize("flags", ["", "-rw-r--r", "x", "---------"])
    def test_short_or_empty_flags_return_empty(self, action, flags) -> None:
        """Test flag strings shorter than ten characters yield {}."""
        assert action._stat_permission_booleans(flags) == {}


class TestParseEncodingFromDesc:
    """Tests for _parse_encoding_from_desc."""

    @pytest.mark.parametrize(
        "desc,expected",
        [
            ("ASCII text", "us-ascii"),
            ("C source, ASCII text", "us-ascii"),
            # OpenBSD has no magic for UTF-8 and describes a UTF-8
            # file this way. The mapper still answers iso-8859-1,
            # which is the right reading of the description; the bytes
            # settle which of the two it really is downstream, in
            # _utf8_overrules_single_byte
            ("ISO-8859 text", "iso-8859-1"),
            ("ISO 8859 text", "iso-8859-1"),
            ("ISO-8859 text, with very long lines", "iso-8859-1"),
            ("UTF-8 Unicode text", "utf-8"),
            ("Little-endian UTF-16 Unicode text", "utf-16"),
            ("Non-ISO extended-ASCII text", "utf-8"),
            ("Non-ISO extended-ASCII text, with LF line terminators", "utf-8"),
            ("Algol 68 source text", "utf-8"),
            ("data", "binary"),
            ("empty", "binary"),
            ("PDF document, version 1.4", "binary"),
            ("", "binary"),
        ],
    )
    def test_descriptions_map_to_encodings(
        self, action, desc, expected
    ) -> None:
        """Test file -b descriptions map to the expected encoding."""
        assert action._parse_encoding_from_desc(desc) == expected


class TestGetReadCommands:
    """Tests for _get_read_commands."""

    def test_minimal_detection_mode(self, action) -> None:
        """Test a bare request probes ls plus both stat variants."""
        commands = action._get_read_commands(["/etc/hosts"], {})

        assert commands == {
            "/etc/hosts_ls": ["ls", "-dn", "/etc/hosts"],
            "/etc/hosts_inode": ["stat", "-c", "%i", "/etc/hosts"],
            "/etc/hosts_inode_bsd": ["stat", "-f", "%i", "/etc/hosts"],
        }

    def test_empty_platform_dict_means_detection_mode(self, action) -> None:
        """Test an empty capabilities dict probes exactly like None."""
        options = {"attributes": True, "md5": True, "sha256": True}

        assert action._get_read_commands(
            ["/f"], options, platform={}
        ) == action._get_read_commands(["/f"], options, platform=None)

    def test_empty_platform_dict_still_probes_hashes(self, action) -> None:
        """Test a checksum request with no knowledge emits hash probes."""
        commands = action._get_read_commands(
            ["/f"], {"md5": True}, platform={}
        )

        # Without normalization the hash branches read {} as a platform
        # with no hash tools and the checksum silently vanished
        assert commands["/f_md5"] == ["md5sum", "/f"]
        assert commands["/f_md5_bsd"] == ["md5", "-q", "/f"]

    def test_gnu_platform_drops_bsd_inode_probe(self, action) -> None:
        """Test a known GNU platform only runs the GNU inode command."""
        commands = action._get_read_commands(
            ["/f"], {}, platform={"stat_variant": "gnu"}
        )

        assert commands == {
            "/f_ls": ["ls", "-dn", "/f"],
            "/f_inode": ["stat", "-c", "%i", "/f"],
        }

    def test_bsd_platform_drops_gnu_inode_probe(self, action) -> None:
        """Test a known BSD platform only runs the BSD inode command."""
        commands = action._get_read_commands(
            ["/f"], {}, platform={"stat_variant": "bsd"}
        )

        assert commands == {
            "/f_ls": ["ls", "-dn", "/f"],
            "/f_inode_bsd": ["stat", "-f", "%i", "/f"],
        }

    def test_attributes_detection_mode_runs_all_variants(self, action) -> None:
        """Test attributes without a platform probes every variant."""
        commands = action._get_read_commands(["/f"], {"attributes": True})

        assert sorted(commands) == [
            "/f_acl",
            "/f_acl_macos",
            "/f_acl_nfs4",
            "/f_flags",
            "/f_flags_macos",
            "/f_inode",
            "/f_inode_bsd",
            "/f_ls",
            "/f_selinux",
            "/f_selinux_ls",
            "/f_stat",
            "/f_stat_bsd",
            "permissions_0",
        ]
        assert commands["/f_stat"] == ["stat", "-c", "%Y %Z %W", "/f"]
        assert commands["/f_stat_bsd"] == ["stat", "-f", "%m %c %B", "/f"]
        assert commands["/f_acl"] == ["getfacl", "-p", "/f"]
        assert commands["/f_acl_nfs4"] == ["nfs4_getfacl", "/f"]
        assert commands["/f_acl_macos"] == ["ls", "-le", "/f"]
        assert commands["/f_flags"] == ["lsattr", "-d", "/f"]
        assert commands["/f_flags_macos"] == ["ls", "-ldO", "/f"]
        assert commands["/f_selinux"] == ["stat", "-c", "%C", "/f"]
        assert commands["/f_selinux_ls"] == ["ls", "-Zd", "/f"]

    def test_extended_implies_attributes_and_adds_xattrs(self, action) -> None:
        """Test extended turns on attribute and xattr commands."""
        commands = action._get_read_commands(["/f"], {"extended": True})

        assert commands["/f_xattr"] == [
            "getfattr",
            "--absolute-names",
            "-d",
            "/f",
        ]
        assert commands["/f_xattr_macos"] == ["xattr", "-lx", "/f"]
        assert "/f_stat" in commands
        assert "/f_acl" in commands

    def test_known_platform_selects_single_variants(self, action) -> None:
        """Test a BSD/macOS platform keeps only the BSD command set."""
        platform = {
            "stat_variant": "bsd",
            "has_lsattr": False,
            "has_getfacl": False,
            "has_nfs4_getfacl": False,
            "has_getfattr": False,
            "has_xattr": True,
            "ls_supports_selinux": False,
            "ls_supports_acl_macos": True,
            "ls_supports_flags_bsd": True,
        }

        commands = action._get_read_commands(
            ["/f"], {"extended": True}, platform=platform
        )

        assert sorted(commands) == [
            "/f_acl_macos",
            "/f_flags_macos",
            "/f_inode_bsd",
            "/f_ls",
            "/f_stat_bsd",
            "/f_xattr_macos",
            "permissions_0",
        ]

    @pytest.mark.parametrize(
        "options",
        [
            {"content": True},
            {"lines": True},
            {"content": True, "encoding": "utf-8"},
            {"content": True, "attributes": True},
        ],
    )
    def test_content_is_never_read_in_this_batch(
        self, action, options
    ) -> None:
        """Test no content command joins the batch that types a path."""
        commands = action._get_read_commands(["/f"], options)

        # cat blocks forever on a FIFO, so it may not travel with the
        # ls that discovers whether the path is a FIFO at all
        assert "/f_cat" not in commands
        assert "/f_encoding" not in commands
        assert "/f_encoding_bsd" not in commands
        assert "/f_encoding_desc" not in commands

    def test_content_request_still_probes_metadata(self, action) -> None:
        """Test a content request keeps the ordinary metadata commands."""
        commands = action._get_read_commands(["/f"], {"content": True})

        assert sorted(commands) == [
            "/f_inode",
            "/f_inode_bsd",
            "/f_ls",
        ]

    def test_mime_requests_both_file_variants(self, action) -> None:
        """Test mime adds the GNU and BSD file invocations."""
        commands = action._get_read_commands(["/f"], {"mime": True})

        assert commands["/f_mimetype"] == [
            "file",
            "-b",
            "--mime-type",
            "/f",
        ]
        assert commands["/f_mimetype_bsd"] == ["file", "-b", "-I", "/f"]

    def test_hash_detection_mode_runs_all_variants(self, action) -> None:
        """Test hashes without a platform probe every known tool."""
        options = {
            "md5": True,
            "sha1": True,
            "sha256": True,
            "sha512": True,
        }

        commands = action._get_read_commands(["/f"], options)

        assert commands["/f_md5"] == ["md5sum", "/f"]
        assert commands["/f_md5_bsd"] == ["md5", "-q", "/f"]
        assert commands["/f_sha1"] == ["sha1sum", "/f"]
        assert commands["/f_sha1_shasum"] == ["shasum", "-a", "1", "/f"]
        assert commands["/f_sha1_bsd"] == ["sha1", "-q", "/f"]
        assert commands["/f_sha256_shasum"] == ["shasum", "-a", "256", "/f"]
        assert commands["/f_sha512_shasum"] == ["shasum", "-a", "512", "/f"]

    def test_hash_uses_platform_capability(self, action) -> None:
        """Test a shasum-only platform picks the shasum variants."""
        platform = {"stat_variant": "bsd", "has_shasum": True}
        options = {"sha1": True, "sha256": True}

        commands = action._get_read_commands(
            ["/f"], options, platform=platform
        )

        assert sorted(commands) == [
            "/f_inode_bsd",
            "/f_ls",
            "/f_sha1_shasum",
            "/f_sha256_shasum",
        ]

    def test_dir_contents_adds_listing_per_path(self, action) -> None:
        """Test need_dir_contents adds a listing command per path."""
        commands = action._get_read_commands(
            ["/a", "/b"], {}, need_dir_contents=True
        )

        assert commands["/a_contents"] == ["ls", "-1A", "/a"]
        assert commands["/b_contents"] == ["ls", "-1A", "/b"]

    def test_multiple_paths_are_keyed_by_path(self, action) -> None:
        """Test each path gets its own prefixed command entries."""
        commands = action._get_read_commands(["/a", "/b"], {})

        assert sorted(commands) == [
            "/a_inode",
            "/a_inode_bsd",
            "/a_ls",
            "/b_inode",
            "/b_inode_bsd",
            "/b_ls",
        ]

    def test_no_paths_yields_no_commands(self, action) -> None:
        """Test an empty path list produces an empty command dict."""
        assert action._get_read_commands([], {"attributes": True}) == {}


class TestGetContentCommands:
    """Tests for _get_content_commands."""

    def test_content_adds_cat_and_encoding_probes(self, action) -> None:
        """Test content asks for cat plus all three encoding probes."""
        commands = action._get_content_commands(["/f"], {"content": True})

        assert commands == {
            "/f_cat": {"command": ["cat", "/f"], "strip": False},
            "/f_encoding": ["file", "-b", "--mime-encoding", "/f"],
            "/f_encoding_bsd": ["file", "-b", "-I", "/f"],
            "/f_encoding_desc": ["file", "-b", "/f"],
        }

    def test_forced_encoding_skips_detection(self, action) -> None:
        """Test a forced encoding drops the file detection commands."""
        commands = action._get_content_commands(
            ["/f"], {"content": True, "encoding": "utf-8"}
        )

        assert commands == {
            "/f_cat": {"command": ["cat", "/f"], "strip": False}
        }

    def test_cat_alone_opts_out_of_strip(self, action) -> None:
        """Test only the cat asks run to leave its output alone."""
        commands = action._get_content_commands(["/f"], {"content": True})

        assert commands["/f_cat"]["strip"] is False
        for key in ("/f_encoding", "/f_encoding_bsd", "/f_encoding_desc"):
            assert not isinstance(commands[key], dict)

    def test_lines_implies_content(self, action) -> None:
        """Test requesting lines pulls in the content commands."""
        commands = action._get_content_commands(["/f"], {"lines": True})

        assert "/f_cat" in commands
        assert "/f_encoding" in commands

    @pytest.mark.parametrize(
        "options", [{}, {"attributes": True}, {"mime": True, "md5": True}]
    )
    def test_no_content_request_yields_no_commands(
        self, action, options
    ) -> None:
        """Test a read that wants no content plans none."""
        assert action._get_content_commands(["/f"], options) == {}

    def test_no_paths_yields_no_commands(self, action) -> None:
        """Test an empty path list produces an empty command dict."""
        assert action._get_content_commands([], {"content": True}) == {}

    def test_multiple_paths_are_keyed_by_path(self, action) -> None:
        """Test each path gets its own prefixed content entries."""
        commands = action._get_content_commands(
            ["/a", "/b"], {"content": True, "encoding": "utf-8"}
        )

        assert sorted(commands) == ["/a_cat", "/b_cat"]


class TestRegularPathsFromResults:
    """Tests for _regular_paths_from_results and _ls_file_type."""

    @pytest.mark.parametrize(
        "flags,expected",
        [
            ("-rw-r--r--", "regular"),
            ("drwxr-xr-x", "directory"),
            ("lrwxr-xr-x", "link"),
            ("prw-r--r--", "pipe"),
            ("srw-r--r--", "socket"),
            ("crw-r--r--", "character"),
            ("brw-r--r--", "block"),
            ("?rw-r--r--", "unknown"),
            ("", "unknown"),
        ],
    )
    def test_ls_flags_name_the_type(self, action, flags, expected) -> None:
        """Test the first ls flag character names the file type."""
        assert action._ls_file_type({"flags": flags}) == expected

    def test_only_regular_files_are_selected(self, action) -> None:
        """Test a mixed batch yields the regular files alone."""
        results = {
            "/reg_ls": _ls_result("-rw-r--r--", "/reg"),
            "/fifo_ls": _ls_result("prw-r--r--", "/fifo"),
            "/dir_ls": _ls_result("drwxr-xr-x", "/dir"),
            "/link_ls": _ls_result("lrwxr-xr-x", "/link"),
            "/dev_ls": _ls_result("crw-r--r--", "/dev"),
        }

        assert action._regular_paths_from_results(
            results, ["/reg", "/fifo", "/dir", "/link", "/dev"]
        ) == ["/reg"]

    def test_paths_keep_their_request_order(self, action) -> None:
        """Test the selection follows the order the paths came in."""
        results = {
            "/b_ls": _ls_result("-rw-r--r--", "/b"),
            "/a_ls": _ls_result("-rw-r--r--", "/a"),
        }

        assert action._regular_paths_from_results(results, ["/b", "/a"]) == [
            "/b",
            "/a",
        ]

    def test_failed_ls_is_not_regular(self, action) -> None:
        """Test a path ls could not stat is left out."""
        results = {"/gone_ls": {"rc": 1, "stdout": ""}}

        assert action._regular_paths_from_results(results, ["/gone"]) == []

    def test_missing_ls_result_is_not_regular(self, action) -> None:
        """Test a path with no ls result at all is left out."""
        assert action._regular_paths_from_results({}, ["/f"]) == []

    @pytest.mark.parametrize("stdout", ["", "not an ls listing at all"])
    def test_unusable_ls_output_is_not_regular(self, action, stdout) -> None:
        """Test output with no flags to read is left out."""
        results = {"/f_ls": {"rc": 0, "stdout": stdout}}

        assert action._regular_paths_from_results(results, ["/f"]) == []


class TestRunContentCommands:
    """Tests for _run_content_commands."""

    def test_no_batch_without_a_content_request(self) -> None:
        """Test a read wanting no content runs no second batch."""
        action = BatchingReadAction()
        results = {"/f_ls": _ls_result("-rw-r--r--", "/f")}

        counts = action._run_content_commands(
            ["/f"], {"attributes": True}, results
        )

        assert action.batches == []
        assert counts == {"count": 0, "batches": 0}
        assert "/f_cat" not in results

    def test_no_batch_when_nothing_typed_regular(self) -> None:
        """Test a batch of specials and directories reads no content."""
        action = BatchingReadAction()
        results = {
            "/fifo_ls": _ls_result("prw-r--r--", "/fifo"),
            "/dir_ls": _ls_result("drwxr-xr-x", "/dir"),
        }

        counts = action._run_content_commands(
            ["/fifo", "/dir"], {"content": True}, results
        )

        assert action.batches == []
        assert counts == {"count": 0, "batches": 0}

    def test_regular_files_alone_are_read(self) -> None:
        """Test a mixed batch cats the regular file and nothing else."""
        action = BatchingReadAction(
            commands={"/reg_cat": {"rc": 0, "stdout": "hello"}}
        )
        results = {
            "/reg_ls": _ls_result("-rw-r--r--", "/reg"),
            "/fifo_ls": _ls_result("prw-r--r--", "/fifo"),
        }

        counts = action._run_content_commands(
            ["/reg", "/fifo"], {"content": True, "encoding": "utf-8"}, results
        )

        assert action.batches == [
            {"/reg_cat": {"command": ["cat", "/reg"], "strip": False}}
        ]
        assert counts == {"count": 4, "batches": 1}
        # The content results join the first batch's so the caller
        # processes one dictionary
        assert results["/reg_cat"] == {"rc": 0, "stdout": "hello"}
        assert results["/reg_ls"]["rc"] == 0


class TestDetectPlatformFromResults:
    """Tests for _detect_platform_from_results."""

    def test_empty_results_report_no_capabilities(self, action) -> None:
        """Test absent results leave every capability at its default."""
        assert action._detect_platform_from_results({}, "/f") == {
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

    def test_silent_success_splits_by_capability_class(self, action) -> None:
        """Test rc 0 with empty stdout is read per capability class."""
        results = {
            "/f_xattr": {"rc": 0, "stdout": ""},
            "/f_acl_macos": {"rc": 0, "stdout": ""},
            "/f_md5": {"rc": 0, "stdout": ""},
            "/f_acl": {"rc": 0, "stdout": ""},
        }

        platform = action._detect_platform_from_results(results, "/f")

        # Acceptance probes succeed silently: getfattr prints nothing
        # for a file that has no extended attributes
        assert platform["has_getfattr"] is True
        assert platform["ls_supports_acl_macos"] is True
        # A capability consumed as output must produce it: a hash tool
        # with no digest and a getfacl with no entries are not present
        assert platform["has_md5sum"] is False
        assert platform["has_getfacl"] is False

    def test_gnu_toolchain_detected(self, action) -> None:
        """Test GNU command results select the GNU capability set."""
        results = {
            "/f_inode": {"rc": 0, "stdout": "12345\n"},
            "/f_inode_bsd": {"rc": 1, "stdout": ""},
            "/f_flags": {"rc": 0, "stdout": "-------------e- /f\n"},
            "/f_acl": {"rc": 0, "stdout": "user::rw-\n"},
            "/f_xattr": {"rc": 0, "stdout": ""},
            "/f_selinux_ls": {
                "rc": 0,
                "stdout": "unconfined_u:object_r:etc_t:s0 /f\n",
            },
            "/f_md5": {"rc": 0, "stdout": "d41d8cd9 /f\n"},
            "/f_sha256": {"rc": 0, "stdout": "e3b0c442 /f\n"},
        }

        platform = action._detect_platform_from_results(results, "/f")

        assert platform["stat_variant"] == "gnu"
        assert platform["has_lsattr"] is True
        assert platform["has_getfacl"] is True
        assert platform["has_getfattr"] is True
        assert platform["ls_supports_selinux"] is True
        assert platform["has_md5sum"] is True
        assert platform["has_sha256sum"] is True
        assert platform["has_shasum"] is False

    def test_bsd_toolchain_detected(self, action) -> None:
        """Test BSD command results select the BSD capability set."""
        results = {
            "/f_inode": {"rc": 1, "stdout": ""},
            "/f_inode_bsd": {"rc": 0, "stdout": "99\n"},
            "/f_flags_macos": {
                "rc": 0,
                "stdout": "drwxr-xr-x 5 u g - 160 Aug 16 10:00 /f\n",
            },
            "/f_acl_macos": {"rc": 0, "stdout": ""},
            "/f_xattr_macos": {"rc": 0, "stdout": ""},
            "/f_md5_bsd": {"rc": 0, "stdout": "d41d8cd9\n"},
            "/f_sha256_shasum": {"rc": 0, "stdout": "e3b0c442 /f\n"},
        }

        platform = action._detect_platform_from_results(results, "/f")

        assert platform["stat_variant"] == "bsd"
        assert platform["ls_supports_flags_bsd"] is True
        assert platform["ls_supports_acl_macos"] is True
        assert platform["has_xattr"] is True
        assert platform["has_md5_bsd"] is True
        assert platform["has_shasum"] is True

    def test_gnu_stat_rc_zero_with_junk_stdout_falls_back(
        self, action
    ) -> None:
        """Test a non-numeric GNU inode result falls back to BSD."""
        results = {
            "/f_inode": {"rc": 0, "stdout": "stat: illegal option -- c\n"},
            "/f_inode_bsd": {"rc": 0, "stdout": "8675309\n"},
        }

        platform = action._detect_platform_from_results(results, "/f")

        assert platform["stat_variant"] == "bsd"

    def test_selinux_question_mark_is_not_support(self, action) -> None:
        """Test ls -Z printing '?' does not count as SELinux support."""
        results = {"/f_selinux_ls": {"rc": 0, "stdout": "? /f\n"}}

        platform = action._detect_platform_from_results(results, "/f")

        assert platform["ls_supports_selinux"] is False

    @pytest.mark.parametrize(
        "tag,capability",
        [
            ("/f_flags", "has_lsattr"),
            ("/f_acl", "has_getfacl"),
            ("/f_acl_nfs4", "has_nfs4_getfacl"),
            ("/f_md5", "has_md5sum"),
            ("/f_sha1", "has_sha1sum"),
            ("/f_sha256", "has_sha256sum"),
            ("/f_sha512", "has_sha512sum"),
            ("/f_sha1_bsd", "has_sha1_bsd"),
            ("/f_sha256_bsd", "has_sha256_bsd"),
            ("/f_sha512_bsd", "has_sha512_bsd"),
            ("/f_md5_bsd", "has_md5_bsd"),
        ],
    )
    def test_rc_zero_with_empty_stdout_is_not_support(
        self, action, tag, capability
    ) -> None:
        """Test these probes require stdout as well as a zero rc."""
        results = {tag: {"rc": 0, "stdout": ""}}

        platform = action._detect_platform_from_results(results, "/f")

        assert platform[capability] is False

    @pytest.mark.parametrize(
        "tag,capability",
        [
            ("/f_flags_macos", "ls_supports_flags_bsd"),
            ("/f_acl_macos", "ls_supports_acl_macos"),
            ("/f_xattr", "has_getfattr"),
            ("/f_xattr_macos", "has_xattr"),
        ],
    )
    def test_rc_zero_alone_is_support(self, action, tag, capability) -> None:
        """Test these probes accept a zero rc with no stdout at all."""
        results = {tag: {"rc": 0, "stdout": ""}}

        platform = action._detect_platform_from_results(results, "/f")

        assert platform[capability] is True

    def test_shasum_detected_from_any_digest_length(self, action) -> None:
        """Test any successful shasum probe sets has_shasum."""
        results = {"/f_sha512_shasum": {"rc": 0, "stdout": "cf83e1 /f\n"}}

        platform = action._detect_platform_from_results(results, "/f")

        assert platform["has_shasum"] is True


class TestProcessReadResults:
    """Tests for _process_read_results.

    The type an option needs is the one the ls reported, not the one
    the result publishes: attributes decides only what is published.
    """

    EMPTY_MD5 = "d41d8cd98f00b204e9800998ecf8427e"

    def test_checksum_reported_without_attributes(self, action) -> None:
        """Test a hash is reported when the type is unpublished."""
        results = {
            "/f_ls": _ls_result("-rw-r--r--"),
            "/f_md5": {"rc": 0, "stdout": f"{self.EMPTY_MD5}  /f\n"},
        }

        file_data, _facts = action._process_read_results(
            results, ["/f"], {"attributes": False, "md5": True}
        )

        assert file_data["/f"]["md5"] == self.EMPTY_MD5
        assert "type" not in file_data["/f"]

    def test_failed_checksum_raises_without_attributes(self, action) -> None:
        """Test a hash that cannot be taken says so either way."""
        results = {
            "/f_ls": _ls_result("-rw-r--r--"),
            "/f_md5": {"rc": 127, "stdout": ""},
        }

        with pytest.raises(ValueError, match="all hash commands failed"):
            action._process_read_results(
                results, ["/f"], {"attributes": False, "md5": True}
            )

    def test_children_reported_without_attributes(self, action) -> None:
        """Test a listing is reported when the type is unpublished."""
        results = {
            "/d_ls": _ls_result("drwxr-xr-x", "/d"),
            "/d_contents": {"rc": 0, "stdout": "one\ntwo\n"},
        }

        file_data, _facts = action._process_read_results(
            results, ["/d"], {"attributes": False}
        )

        assert file_data["/d"]["children"] == ["/d/one", "/d/two"]
        assert "type" not in file_data["/d"]

    def test_an_empty_directory_lists_nothing(self, action) -> None:
        """Test a directory that holds nothing says so with an empty
        list, which is a typed answer and not a silence."""
        results = {
            "/d_ls": _ls_result("drwxr-xr-x", "/d"),
            "/d_contents": {"rc": 0, "stdout": "\n"},
        }

        file_data, _facts = action._process_read_results(
            results, ["/d"], {"attributes": False}
        )

        assert file_data["/d"]["children"] == []

    def test_an_unlistable_directory_omits_its_children(self, action) -> None:
        """Test a directory that would not list leaves children out.

        An empty list is the answer for a directory that holds
        nothing; a listing that was refused is a question that never
        got asked, and filing the one as the other is how a permission
        denial comes back as an empty directory.
        """
        results = {
            "/d_ls": _ls_result("drwx------", "/d"),
            "/d_contents": {"rc": 1, "stdout": "", "stderr": "denied"},
        }

        file_data, _facts = action._process_read_results(
            results, ["/d"], {"attributes": False}
        )

        assert "children" not in file_data["/d"]

    def test_hash_skipped_for_a_directory(self, action) -> None:
        """Test only a regular file is hashed, published type or not."""
        results = {
            "/d_ls": _ls_result("drwxr-xr-x", "/d"),
            "/d_md5": {"rc": 1, "stdout": ""},
        }

        file_data, _facts = action._process_read_results(
            results, ["/d"], {"attributes": False, "md5": True}
        )

        assert "md5" not in file_data["/d"]

    def test_attributes_publish_the_type(self, action) -> None:
        """Test the type is published when attributes are requested."""
        results = {"/f_ls": _ls_result("-rw-r--r--")}

        file_data, _facts = action._process_read_results(
            results, ["/f"], {"attributes": True}
        )

        assert file_data["/f"]["type"] == "regular"

    @pytest.mark.parametrize(
        "flags,xusr",
        [("-rwxr-xr-x", True), ("-rw-r--r--", False)],
    )
    def test_the_mode_bits_are_published_as_read(
        self, action, flags, xusr
    ) -> None:
        """Test what the filesystem asserts is published bit for bit.

        The mode is the filesystem's own claim about the file, and it
        is published as that rather than as an answer about whether
        anybody can run it.
        """
        results = {"/f_ls": _ls_result(flags)}

        file_data, _facts = action._process_read_results(
            results, ["/f"], {"attributes": True}
        )

        assert file_data["/f"]["xusr"] is xusr
        assert file_data["/f"]["rusr"] is True
        assert "executable" not in file_data["/f"]

    def test_type_returned_without_being_published(self, action) -> None:
        """Test the caller is told the type the result withholds.

        Recursion and symlink following depend on the type, so it is
        determined for every path and handed back beside the file data
        whatever attributes decided to publish.
        """
        results = {
            "/d_ls": _ls_result("drwxr-xr-x", "/d"),
            "/l_ls": _ls_result("lrwxrwxrwx", "/l"),
            "/f_ls": _ls_result("-rw-r--r--"),
        }

        file_data, ls_facts = action._process_read_results(
            results, ["/d", "/l", "/f"], {"attributes": False}
        )

        assert ls_facts["/d"]["type"] == "directory"
        assert ls_facts["/l"]["type"] == "link"
        assert ls_facts["/f"]["type"] == "regular"
        assert all("type" not in data for data in file_data.values())

    def test_link_target_returned_without_being_published(
        self, action
    ) -> None:
        """Test the target a link points at travels with its type.

        Following a link recursively needs where it points as much as
        it needs to know that it points, and the same ls entry reports
        both, so attributes governs neither.
        """
        results = {"/l_ls": _ls_link_result("/l", "/target")}

        file_data, ls_facts = action._process_read_results(
            results, ["/l"], {"attributes": False}
        )

        assert ls_facts["/l"] == {"type": "link", "target": "/target"}
        # An entry names what was consulted for it whatever else it
        # publishes, because that is a fact about the entry rather
        # than one of the attributes
        assert file_data["/l"] == {
            "evidence": {"commands": []},
            "origins": ["o0_o.posix.read"],
        }

    def test_link_target_is_published_on_request(self, action) -> None:
        """Test attributes publishes the target it does not decide."""
        results = {"/l_ls": _ls_link_result("/l", "/target")}

        file_data, ls_facts = action._process_read_results(
            results, ["/l"], {"attributes": True}
        )

        assert file_data["/l"]["target"] == "/target"
        assert ls_facts["/l"]["target"] == "/target"

    def test_only_a_link_carries_a_target(self, action) -> None:
        """Test a target is not invented for what cannot have one."""
        results = {"/f_ls": _ls_result("-rw-r--r--")}

        _data, ls_facts = action._process_read_results(
            results, ["/f"], {"attributes": False}
        )

        assert "target" not in ls_facts["/f"]

    def test_missing_path_is_typed_by_neither(self, action) -> None:
        """Test a path with no listing appears in neither mapping.

        A dangling link's target lands here, and the absence is what
        tells the action to leave the link's own data alone.
        """
        results = {"/gone_ls": {"rc": 1, "stdout": ""}}

        file_data, ls_facts = action._process_read_results(
            results, ["/gone"], {"attributes": True}
        )

        assert file_data == {"/gone": None}
        assert ls_facts == {}


def _resolve_result(*steps: str, ended: bool = True) -> dict[str, Any]:
    """Build a resolution walk's result out of the steps it printed."""
    lines = list(steps)
    if ended:
        lines.append(RESOLUTION_END_MARKER)
    return {"rc": 0, "stdout": "\n".join(lines) + "\n"}


class TestResolutionCommand:
    """Tests for the walk _get_read_commands plans."""

    def test_resolve_is_not_planned_unless_asked_for(self, action) -> None:
        """Test a read that did not ask walks nothing."""
        commands = action._get_read_commands(["/f"], {"attributes": True})

        assert "/f_resolve" not in commands

    def test_resolve_plans_one_walk_per_path(self, action) -> None:
        """Test every path gets a walk, links and plain files alike."""
        commands = action._get_read_commands(
            ["/a", "/b"], {"resolve": True}, platform={"stat_variant": "gnu"}
        )

        assert sorted(commands) == [
            "/a_inode",
            "/a_ls",
            "/a_resolve",
            "/b_inode",
            "/b_ls",
            "/b_resolve",
        ]

    def test_the_walk_runs_in_a_posix_shell(self, action) -> None:
        """Test the walk is a sh script, readlink(1) not being POSIX."""
        command = action._resolution_command("/bin/sh")

        assert command[:2] == ["sh", "-c"]
        assert command[2].startswith("p=/bin/sh;")
        assert "readlink" not in command[2]
        assert "pwd -P" in command[2]
        assert "ls -ld" in command[2]

    def test_a_quoted_path_reaches_the_shell_whole(self, action) -> None:
        """Test a path holding a quote is quoted rather than broken."""
        command = action._resolution_command("/tmp/it's here")

        assert command[2].startswith("""p='/tmp/it'"'"'s here';""")


class TestParseResolution:
    """Tests for reading a walk's steps back."""

    def test_a_chain_of_one_is_an_answer(self, action) -> None:
        """Test a path that is only itself resolves to itself."""
        assert action._parse_resolution(
            _resolve_result("/etc/hosts"), "/etc/hosts"
        ) == ["/etc/hosts"]

    def test_every_hop_is_a_step(self, action) -> None:
        """Test a linked directory component is a step of its own."""
        assert action._parse_resolution(
            _resolve_result("/bin/sh", "/usr/bin/sh", "/usr/bin/bash"),
            "/bin/sh",
        ) == ["/bin/sh", "/usr/bin/sh", "/usr/bin/bash"]

    def test_a_broken_chain_records_the_step_that_is_not_there(
        self, action
    ) -> None:
        """Test the path a dangling link names is the last step."""
        assert action._parse_resolution(
            _resolve_result("/tmp/dangling", "/tmp/gone"), "/tmp/dangling"
        ) == ["/tmp/dangling", "/tmp/gone"]

    def test_a_walk_that_did_not_run_answers_nothing(self, action) -> None:
        """Test a failed walk is a silence rather than a chain."""
        assert (
            action._parse_resolution({"rc": 1, "stdout": ""}, "/f") is None
        )

    def test_an_empty_walk_answers_nothing(self, action) -> None:
        """Test a walk that printed nothing is not a chain of none."""
        assert action._parse_resolution({"rc": 0, "stdout": ""}, "/f") is None

    def test_a_cycle_fails_and_names_itself(self, action) -> None:
        """Test a chain returning to a path it visited is a fault."""
        with pytest.raises(ValueError) as excinfo:
            action._parse_resolution(
                _resolve_result("/a", "/b", "/a", "/b", ended=False), "/a"
            )

        message = str(excinfo.value)
        assert "/a" in message
        assert "/b" in message
        assert "never ends" in message

    def test_a_walk_cut_off_at_the_ceiling_is_a_cycle(self, action) -> None:
        """Test a walk that never ended fails even with no repeat."""
        steps = [f"/step{index}" for index in range(RESOLUTION_MAX_HOPS)]

        with pytest.raises(ValueError) as excinfo:
            action._parse_resolution(
                _resolve_result(*steps, ended=False), "/step0"
            )

        assert str(RESOLUTION_MAX_HOPS) in str(excinfo.value)


class TestResolutionIsPublished:
    """Tests for where a chain lands once it has been read."""

    def test_the_chain_is_published_with_the_attributes(self, action) -> None:
        """Test a resolved read carries the chain it walked."""
        results = {
            "/l_ls": _ls_link_result("/l", "/target"),
            "/l_resolve": _resolve_result("/l", "/target"),
        }

        file_data, ls_facts = action._process_read_results(
            results, ["/l"], {"attributes": True, "resolve": True}
        )

        assert file_data["/l"]["resolution"] == ["/l", "/target"]
        assert ls_facts["/l"]["resolution"] == ["/l", "/target"]

    def test_the_chain_survives_attributes_being_off(self, action) -> None:
        """Test a chain asked for by name is published regardless."""
        results = {
            "/l_ls": _ls_link_result("/l", "/target"),
            "/l_resolve": _resolve_result("/l", "/target"),
        }

        file_data, _facts = action._process_read_results(
            results, ["/l"], {"attributes": False, "resolve": True}
        )

        assert file_data["/l"] == {
            "resolution": ["/l", "/target"],
            "evidence": {"commands": []},
            "origins": ["o0_o.posix.read"],
        }

    def test_no_chain_key_where_none_was_asked_for(self, action) -> None:
        """Test a read that did not resolve publishes no chain."""
        results = {"/f_ls": _ls_result("-rw-r--r--")}

        file_data, ls_facts = action._process_read_results(
            results, ["/f"], {"attributes": True}
        )

        assert "resolution" not in file_data["/f"]
        assert "resolution" not in ls_facts["/f"]

    def test_a_cycle_takes_the_whole_read_down(self, action) -> None:
        """Test the cycle is reported rather than a truncated chain."""
        results = {
            "/a_ls": _ls_link_result("/a", "/b"),
            "/a_resolve": _resolve_result("/a", "/b", "/a", ended=False),
        }

        with pytest.raises(ValueError) as excinfo:
            action._process_read_results(
                results, ["/a"], {"attributes": True, "resolve": True}
            )

        assert "never ends" in str(excinfo.value)


class _PlayContext:
    """The two things a probe reads off a play context."""

    def __init__(
        self,
        become: bool = False,
        become_user: Optional[str] = None,
        remote_user: Optional[str] = None,
    ) -> None:
        self.become = become
        self.become_user = become_user
        self.remote_user = remote_user
        self.connection_user = remote_user


def _probe_result(uid: str, rows: dict[str, str]) -> dict[str, Any]:
    """Build one permission probe's result out of the rows it printed."""
    lines = [uid] + [f"{answers} {path}" for path, answers in rows.items()]
    return {"rc": 0, "stdout": "\n".join(lines) + "\n"}


class TestPermissionProbeUsers:
    """Tests for whose answers a permission probe collects."""

    def test_without_become_only_this_user_answers(self, action) -> None:
        """Test a task running as itself asks as itself and stops."""
        assert action._permission_probe_users() == [None]

    def test_become_to_root_also_asks_as_the_connection_user(
        self, action
    ) -> None:
        """Test become is exactly what makes one row not two."""
        action._play_context = _PlayContext(
            become=True, become_user="root", remote_user="o0-o"
        )

        assert action._permission_probe_users() == [None, "o0-o"]

    def test_become_without_a_user_named_is_root(self, action) -> None:
        """Test the Ansible default is read as the drop it is."""
        action._play_context = _PlayContext(become=True, remote_user="o0-o")

        assert action._permission_probe_users() == [None, "o0-o"]

    def test_nobody_but_root_drops(self, action) -> None:
        """Test a become to somebody else asks as itself and stops.

        su asks everyone but root for a password, on a terminal a
        probe does not have, so the drop would hang rather than
        answer.
        """
        action._play_context = _PlayContext(
            become=True, become_user="postgres", remote_user="o0-o"
        )

        assert action._permission_probe_users() == [None]

    def test_a_root_connection_is_not_dropped_to(self, action) -> None:
        """Test connecting as root and becoming root is one identity."""
        action._play_context = _PlayContext(
            become=True, become_user="root", remote_user="root"
        )

        assert action._permission_probe_users() == [None]


class TestPermissionCommands:
    """Tests for the probes _get_read_commands plans."""

    def test_attributes_ask_the_kernel_rather_than_the_mode(
        self, action
    ) -> None:
        """Test a read with attributes asks test about every path."""
        commands = action._get_read_commands(
            ["/a", "/b"],
            {"attributes": True},
            platform={"stat_variant": "gnu"},
        )

        assert commands["permissions_0"]["command"][:2] == ["sh", "-c"]
        script = commands["permissions_0"]["command"][2]
        assert script.startswith("id -u;")
        assert "for p in /a /b; do" in script
        assert 'test -r "$p"' in script
        assert 'test -w "$p"' in script
        assert 'test -x "$p"' in script

    def test_one_shell_answers_for_every_path(self, action) -> None:
        """Test the batch holds one probe, not one probe per path."""
        commands = action._get_read_commands(
            ["/a", "/b", "/c"],
            {"attributes": True},
            platform={"stat_variant": "gnu"},
        )

        probes = [key for key in commands if key.startswith("permissions_")]
        assert probes == ["permissions_0"]

    def test_a_read_without_attributes_asks_nothing(self, action) -> None:
        """Test a content read pays for no permission probe."""
        commands = action._get_read_commands(["/a"], {"content": True})

        assert [
            key for key in commands if key.startswith("permissions_")
        ] == []

    def test_a_dropped_probe_runs_the_same_script_through_su(
        self, action
    ) -> None:
        """Test the second identity asks the same thing as the first."""
        action._play_context = _PlayContext(
            become=True, become_user="root", remote_user="o0-o"
        )

        commands = action._get_read_commands(
            ["/a"], {"attributes": True}, platform={"stat_variant": "gnu"}
        )

        assert commands["permissions_1"]["command"][:4] == [
            "su",
            "-s",
            "/bin/sh",
            "o0-o",
        ]
        assert commands["permissions_1"]["command"][4] == "-c"
        assert (
            commands["permissions_1"]["command"][5]
            == commands["permissions_0"]["command"][2]
        )

    def test_no_paths_is_no_probe(self, action) -> None:
        """Test an empty batch does not build a for loop over nothing."""
        assert action._get_permission_commands([]) == {}


class TestProcessPermissionProbes:
    """Tests for reading the probes back into rows."""

    def test_a_row_is_keyed_by_the_uid_that_asked(self, action) -> None:
        """Test each answer is filed under whoever was told it."""
        results = {"permissions_0": _probe_result("0", {"/f": "rw-"})}

        assert action._process_permission_probes(results, ["/f"]) == {
            "/f": {
                "readable": {"0": True},
                "writable": {"0": True},
                "executable": {"0": False},
            }
        }

    def test_two_identities_answer_side_by_side(self, action) -> None:
        """Test root and the connection user both get a row.

        Root reading what the mode would refuse everybody is the
        expected answer and the reason the rows are kept apart.
        """
        results = {
            "permissions_0": _probe_result("0", {"/f": "rw-"}),
            "permissions_1": _probe_result("1000", {"/f": "---"}),
        }

        assert action._process_permission_probes(results, ["/f"]) == {
            "/f": {
                "readable": {"0": True, "1000": False},
                "writable": {"0": True, "1000": False},
                "executable": {"0": False, "1000": False},
            }
        }

    def test_a_probe_that_did_not_run_writes_no_row(self, action) -> None:
        """Test a refused su leaves its rows out rather than guessed."""
        results = {
            "permissions_0": _probe_result("0", {"/f": "rwx"}),
            "permissions_1": {"rc": 1, "stdout": ""},
        }

        assert action._process_permission_probes(results, ["/f"]) == {
            "/f": {
                "readable": {"0": True},
                "writable": {"0": True},
                "executable": {"0": True},
            }
        }

    def test_a_shell_that_would_not_say_who_it_is_answers_nothing(
        self, action
    ) -> None:
        """Test a row with nobody's name on it is not a row."""
        results = {
            "permissions_0": {"rc": 0, "stdout": "who knows\nrwx /f\n"}
        }

        assert action._process_permission_probes(results, ["/f"]) == {}

    def test_a_line_about_a_path_nobody_asked_about_is_dropped(
        self, action
    ) -> None:
        """Test the probe answers for the batch and nothing else."""
        results = {
            "permissions_0": _probe_result(
                "0", {"/f": "rwx", "/elsewhere": "rwx"}
            )
        }

        assert list(action._process_permission_probes(results, ["/f"])) == [
            "/f"
        ]

    def test_a_row_that_does_not_parse_is_dropped(self, action) -> None:
        """Test a malformed answer is not read as three falses."""
        results = {"permissions_0": {"rc": 0, "stdout": "0\nrw /f\n"}}

        assert action._process_permission_probes(results, ["/f"]) == {}


class TestPermissionsArePublished:
    """Tests for where the rows land once they have been read."""

    def test_the_triple_is_the_probe_and_not_the_mode(self, action) -> None:
        """Test the published triple is what the kernel answered.

        The mode here would say the owner can write; the probe says
        nobody could, which is what a read-only mount looks like, and
        the published answer is the probe's.
        """
        results = {
            "/f_ls": _ls_result("-rw-r--r--"),
            "permissions_0": _probe_result("0", {"/f": "r--"}),
        }

        file_data, _facts = action._process_read_results(
            results, ["/f"], {"attributes": True}
        )

        assert file_data["/f"]["readable"] == {"0": True}
        assert file_data["/f"]["writable"] == {"0": False}
        assert file_data["/f"]["executable"] == {"0": False}
        assert file_data["/f"]["wusr"] is True

    def test_no_probe_leaves_the_triple_unmentioned(self, action) -> None:
        """Test a path nobody asked about carries no answer at all."""
        results = {"/f_ls": _ls_result("-rw-r--r--")}

        file_data, _facts = action._process_read_results(
            results, ["/f"], {"attributes": True}
        )

        assert "readable" not in file_data["/f"]
        assert "writable" not in file_data["/f"]
        assert "executable" not in file_data["/f"]


class TestEntriesNameWhatWasConsulted:
    """Tests for the evidence a read files on each entry."""

    def test_an_entry_names_the_commands_asked_about_it(
        self, action
    ) -> None:
        """Test what ran for a path is what that path's entry names."""
        commands = action._get_read_commands(
            ["/f"], {"attributes": True}, platform={"stat_variant": "gnu"}
        )
        results = {"/f_ls": _ls_result("-rw-r--r--")}

        file_data, _facts = action._process_read_results(
            results, ["/f"], {"attributes": True}, commands=commands
        )

        # The permission probe's logic is test, not the sh that read
        # the script back
        assert file_data["/f"]["evidence"] == {
            "commands": ["ls", "stat", "test"]
        }

    def test_a_read_reads_no_file_as_evidence(self, action) -> None:
        """Test only commands are named.

        Every probe here is run at the path itself, and the bytes of
        the path are the fact rather than evidence for it, so files is
        a kind this producer does not have rather than one it attempts
        and fills with nothing.
        """
        commands = action._get_read_commands(["/f"], {})
        results = {"/f_ls": _ls_result("-rw-r--r--")}

        file_data, _facts = action._process_read_results(
            results, ["/f"], {}, commands=commands
        )

        assert "files" not in file_data["/f"]["evidence"]

    def test_each_path_names_what_was_asked_about_it(self, action) -> None:
        """Test a batch's commands are sorted by the path each names.

        The one that names no path is a probe that answered for every
        path at once, and belongs to all of them.
        """
        commands = {
            "/a_ls": ["ls", "-dn", "/a"],
            "/b_ls": ["ls", "-dn", "/b"],
            "/b_md5": ["md5sum", "/b"],
            "permissions_0": ["sh", "-c", "id -u"],
        }
        results = {
            "/a_ls": _ls_result("-rw-r--r--", "/a"),
            "/b_ls": _ls_result("-rw-r--r--", "/b"),
        }

        file_data, _facts = action._process_read_results(
            results, ["/a", "/b"], {"attributes": True}, commands=commands
        )

        assert file_data["/a"]["evidence"] == {"commands": ["ls", "sh"]}
        assert file_data["/b"]["evidence"] == {
            "commands": ["ls", "md5sum", "sh"]
        }

    def test_a_key_belongs_to_the_longest_path_that_prefixes_it(
        self, action
    ) -> None:
        """Test a path whose name looks like another's key is its own.

        A key is a path and a suffix, and a suffix never holds a
        slash, so the longest path that prefixes a key is the path the
        key is about.
        """
        by_path, shared = action._commands_by_path(
            {
                "/f_ls": ["ls", "-dn", "/f"],
                "/f_ls_ls": ["ls", "-dn", "/f_ls"],
                "permissions_0": ["sh", "-c", "id -u"],
            },
            ["/f", "/f_ls"],
        )

        assert by_path == {"/f": ["ls"], "/f_ls": ["ls"]}
        assert shared == ["sh"]

    def test_a_read_that_kept_no_batch_names_nothing(self, action) -> None:
        """Test an entry says the kind was attempted and answered for
        nothing rather than claiming a command nobody recorded."""
        results = {"/f_ls": _ls_result("-rw-r--r--")}

        file_data, _facts = action._process_read_results(
            results, ["/f"], {"attributes": True}
        )

        assert file_data["/f"]["evidence"] == {"commands": []}


class TestScriptProbesNameWhatTheyAsk:
    """Tests for the one case an evidence name is declared."""

    def test_the_permission_probe_names_test(self, action) -> None:
        """Test the probe names its logic rather than its interpreter.

        A name derives from argv, which is right for a command run as
        a command. This probe's logic is a script, so argv would name
        the sh that read it back, and sh is not what was asked.
        """
        commands = action._get_permission_commands(["/f"])

        assert commands["permissions_0"]["evidence"] == ["test"]

    def test_a_dropped_probe_names_the_su_it_execs(self, action) -> None:
        """Test su is named, because su really is run as a command."""
        action._play_context = _PlayContext(
            become=True, become_user="root", remote_user="o0-o"
        )

        commands = action._get_permission_commands(["/f"])

        assert commands["permissions_1"]["evidence"] == ["su", "test"]

    def test_the_resolution_walk_names_what_it_walks_with(
        self, action
    ) -> None:
        """Test the walk names cd, pwd and ls rather than sh."""
        commands = action._get_read_commands(["/f"], {"resolve": True})

        assert commands["/f_resolve"]["evidence"] == ["cd", "ls", "pwd"]

    def test_a_declared_name_supersedes_the_derivation(
        self, action
    ) -> None:
        """Test the override wins where a request declares one."""
        assert action._command_evidence(
            {"command": ["sh", "-c", "test -r /f"], "evidence": ["test"]}
        ) == ["test"]

    def test_a_plain_request_still_derives_its_name(self, action) -> None:
        """Test nothing else changes: argv is the default everywhere."""
        assert action._command_evidence(["ls", "-dn", "/f"]) == ["ls"]
        assert action._command_evidence(
            {"command": ["cat", "/f"], "strip": False}
        ) == ["cat"]

    def test_a_declared_empty_list_names_nothing(self, action) -> None:
        """Test a request may declare that it evidences nothing."""
        assert action._command_evidence(
            {"command": ["sh", "-c", ":"], "evidence": []}
        ) == []

    def test_the_walk_and_the_listing_share_the_ls_they_both_run(
        self, action
    ) -> None:
        """Test a name two probes contribute is named once.

        The walk reads link text with ls and the metadata read lists
        the path with it, and the evidence holds one of each name.
        """
        commands = action._get_read_commands(
            ["/f"],
            {"attributes": True, "resolve": True},
            platform={"stat_variant": "gnu"},
        )
        results = {"/f_ls": _ls_result("-rw-r--r--")}

        file_data, _facts = action._process_read_results(
            results, ["/f"], {"attributes": True}, commands=commands
        )

        assert file_data["/f"]["evidence"]["commands"] == [
            "cd",
            "ls",
            "pwd",
            "stat",
            "test",
        ]
