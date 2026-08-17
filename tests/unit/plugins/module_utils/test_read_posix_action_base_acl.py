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

"""Unit tests for the ReadPosixActionBase ACL parsers."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

import pytest

try:
    from ansible_collections.o0_o.posix.plugins.module_utils.read_posix_action_base import (  # type: ignore  # noqa: E501
        ReadPosixActionBase,
    )
except ModuleNotFoundError:  # pragma: no cover - ansible missing in tests
    ReadPosixActionBase = None  # type: ignore

pytestmark = pytest.mark.skipif(
    ReadPosixActionBase is None, reason="ansible package is required"
)


class DummyReadAction(ReadPosixActionBase):
    """Minimal ReadPosixActionBase subclass with no Ansible plumbing."""

    def __init__(self) -> None:
        self.inventory_hostname = "testhost"


@pytest.fixture
def action() -> DummyReadAction:
    """Provide a bare ReadPosixActionBase instance per test."""
    return DummyReadAction()


@pytest.fixture
def sample() -> Callable[[str], str]:
    """Read a sample tool capture from the files directory.

    The samples under files/ are constructed to match the documented
    output of getfacl, nfs4_getfacl and ls -le. They were written by
    hand, not captured from a live host.
    """

    def _read(name: str) -> str:
        return (Path(__file__).parent / "files" / name).read_text()

    return _read


class TestParseMacosAcl:
    """Tests for _parse_macos_acl."""

    def test_directory_acl_with_inheritance(self, action, sample) -> None:
        """Test a full ls -le capture maps to normalized entries."""
        acl = action._parse_macos_acl(sample("acl_macos_ls_le.txt"))

        assert acl == {
            "type": "macos",
            "entries": [
                {
                    "type": "group",
                    "name": "everyone",
                    "delete": False,
                },
                {
                    "type": "user",
                    "name": "john",
                    "read": True,
                    "write": True,
                    "execute": True,
                    "delete": True,
                    "append": True,
                    "delete_child": True,
                    "chown": True,
                    "attributes": {"read": True, "write": True},
                    "extended": {"read": True, "write": True},
                    "security": {"read": True, "write": True},
                    "inheritance": {
                        "file": True,
                        "directory": True,
                        "propagate": True,
                    },
                },
                {
                    "type": "group",
                    "name": "staff",
                    "read": True,
                    "execute": True,
                    "attributes": {"read": True},
                    "extended": {"read": True},
                    "security": {"read": True},
                    "inheritance": {
                        "file": True,
                        "directory": True,
                        "propagate": False,
                    },
                },
            ],
        }

    def test_deny_entry_sets_rights_false(self, action) -> None:
        """Test a deny ACE records its rights as false."""
        acl = action._parse_macos_acl(" 0: group:everyone deny write,delete")

        assert acl["entries"] == [
            {
                "type": "group",
                "name": "everyone",
                "write": False,
                "delete": False,
            }
        ]

    @pytest.mark.parametrize(
        "right,expected_key",
        [
            ("list", "read"),
            ("list_directory", "read"),
            ("read_data", "read"),
            ("add_file", "write"),
            ("write_data", "write"),
            ("search", "execute"),
            ("add_subdirectory", "append"),
            ("append_data", "append"),
        ],
    )
    def test_directory_rights_are_aliased(
        self, action, right, expected_key
    ) -> None:
        """Test directory right names normalize to file right names."""
        acl = action._parse_macos_acl(f" 0: user:bob allow {right}")

        assert acl["entries"][0][expected_key] is True

    def test_rights_may_be_space_separated(self, action) -> None:
        """Test rights split on whitespace as well as commas."""
        acl = action._parse_macos_acl(" 0: user:bob allow read write")

        assert acl["entries"][0]["read"] is True
        assert acl["entries"][0]["write"] is True

    def test_inherited_as_trailing_right(self, action) -> None:
        """Test a trailing inherited token sets the inherited flag."""
        acl = action._parse_macos_acl(" 0: user:bob allow read,inherited")

        assert acl["entries"] == [
            {
                "type": "user",
                "name": "bob",
                "read": True,
                "inherited": True,
            }
        ]

    def test_inherited_before_permission_word_misparses(self, action) -> None:
        """Test an inherited allow ACE is read as a deny (known bug)."""
        acl = action._parse_macos_acl(
            " 0: user:john inherited allow read,write"
        )

        # 'inherited' is captured as the permission word, so the allow
        # keyword lands in the rights list and every right reads false.
        assert acl["entries"] == [
            {
                "type": "user",
                "name": "john",
                "read": False,
                "write": False,
            }
        ]

    def test_unknown_rights_are_dropped(self, action) -> None:
        """Test rights outside the known vocabulary are ignored."""
        acl = action._parse_macos_acl(" 0: user:bob allow read,frobnicate")

        assert acl["entries"] == [
            {"type": "user", "name": "bob", "read": True}
        ]

    def test_only_inherit_without_file_or_directory(self, action) -> None:
        """Test only_inherit alone is kept without a propagate key."""
        acl = action._parse_macos_acl(" 0: user:bob allow read,only_inherit")

        assert acl["entries"][0]["inheritance"] == {"only": True}

    @pytest.mark.parametrize(
        "text",
        [
            "",
            "-rw-r--r-- 1 john staff 0 Aug 16 10:01 /tmp/x\n",
            " 0: garbage-line\n",
            "no acl entries here\n",
        ],
    )
    def test_no_matching_lines_yields_empty_entries(
        self, action, text
    ) -> None:
        """Test non-ACE input still returns the macos ACL envelope."""
        assert action._parse_macos_acl(text) == {
            "type": "macos",
            "entries": [],
        }

    def test_malformed_lines_are_skipped(self, action) -> None:
        """Test only well formed ACE lines contribute entries."""
        text = (
            " 0: garbage-line\n"
            " x: user:bob allow read\n"
            " 1: user:bob allow read\n"
        )

        acl = action._parse_macos_acl(text)

        assert acl["entries"] == [
            {"type": "user", "name": "bob", "read": True}
        ]


class TestParsePosixAcl:
    """Tests for _parse_posix_acl."""

    def test_extended_and_default_entries(self, action, sample) -> None:
        """Test a full getfacl capture maps to extended entries."""
        acl = action._parse_posix_acl(sample("acl_posix_getfacl.txt"))

        assert acl == {
            "type": "posix",
            "entries": [
                {
                    "type": "user",
                    "name": "john",
                    "read": True,
                    "execute": True,
                },
                {
                    "type": "group",
                    "name": "devs",
                    "read": True,
                    "write": True,
                    "execute": True,
                },
                {
                    "type": "mask",
                    "read": True,
                    "write": True,
                    "execute": True,
                },
                # The default: entries below lose their principal and
                # their permissions: the parser reads parts[1] as the
                # name and parts[2] as the perms, which for a
                # default:user:john:r-x line are 'user' and 'john'.
                {"type": "default", "name": "user"},
                {"type": "default", "name": "user"},
                {"type": "default", "name": "group"},
                {"type": "default", "name": "mask"},
                {"type": "default", "name": "other"},
            ],
        }

    def test_basic_permissions_only(self, action) -> None:
        """Test a file with no extended ACL yields no entries."""
        text = (
            "# file: /etc/hosts\n"
            "# owner: root\n"
            "# group: root\n"
            "user::rw-\n"
            "group::r--\n"
            "other::r--\n"
        )

        assert action._parse_posix_acl(text) == {
            "type": "posix",
            "entries": [],
        }

    def test_named_user_permission_booleans(self, action) -> None:
        """Test only the granted permission keys are present."""
        acl = action._parse_posix_acl("user:john:r-x\n")

        assert acl["entries"] == [
            {
                "type": "user",
                "name": "john",
                "read": True,
                "execute": True,
            }
        ]

    def test_no_permissions_entry_has_no_boolean_keys(self, action) -> None:
        """Test an entry with --- carries no permission keys."""
        acl = action._parse_posix_acl("user:john:---\n")

        assert acl["entries"] == [{"type": "user", "name": "john"}]

    def test_mask_entry_is_extended(self, action) -> None:
        """Test the mask entry is kept even though it is unnamed."""
        acl = action._parse_posix_acl("mask::r-x\n")

        assert acl["entries"] == [
            {"type": "mask", "read": True, "execute": True}
        ]

    @pytest.mark.parametrize("line", ["user::rwx", "group::r-x", "other::r--"])
    def test_basic_unnamed_entries_are_skipped(self, action, line) -> None:
        """Test owner, group owner and other entries are excluded."""
        assert action._parse_posix_acl(line)["entries"] == []

    @pytest.mark.parametrize(
        "text",
        ["", "\n\n", "# file: /etc/hosts\n", "garbage\n", "user:john\n"],
    )
    def test_empty_or_malformed_input(self, action, text) -> None:
        """Test blank, comment and short lines produce no entries."""
        assert action._parse_posix_acl(text) == {
            "type": "posix",
            "entries": [],
        }

    def test_effective_comment_is_read_as_permissions(self, action) -> None:
        """Test a trailing #effective comment stays inside the perms."""
        acl = action._parse_posix_acl("user:john:rwx\t#effective:r-x\n")

        # The masked-down effective rights are not applied; the raw
        # rwx field is what is reported.
        assert acl["entries"] == [
            {
                "type": "user",
                "name": "john",
                "read": True,
                "write": True,
                "execute": True,
            }
        ]


class TestParseNfs4Acl:
    """Tests for _parse_nfs4_acl."""

    def test_full_acl_capture(self, action, sample) -> None:
        """Test a full nfs4_getfacl capture maps to normalized ACEs."""
        acl = action._parse_nfs4_acl(sample("acl_nfs4_getfacl.txt"))

        assert acl == {
            "type": "nfs4",
            "entries": [
                {
                    "type": "owner",
                    "read": True,
                    "write": True,
                    "append": True,
                    "delete_child": True,
                    "execute": True,
                    "chown": True,
                    "synchronize": True,
                    "attributes": {"read": True, "write": True},
                    "extended": {"read": True, "write": True},
                    "security": {"read": True, "write": True},
                },
                {
                    "type": "group_owner",
                    "read": True,
                    "execute": True,
                    "synchronize": True,
                    "attributes": {"read": True},
                    "extended": {"read": True},
                    "security": {"read": True},
                },
                {
                    "type": "everyone",
                    "read": True,
                    "execute": True,
                    "synchronize": True,
                    "attributes": {"read": True},
                    "extended": {"read": True},
                    "security": {"read": True},
                },
                {
                    "type": "user",
                    "name": "john@example.com",
                    "read": True,
                    "write": True,
                    "append": True,
                    "execute": True,
                    "synchronize": True,
                    "attributes": {"read": True},
                    "security": {"read": True},
                    "inheritance": {
                        "file": True,
                        "directory": True,
                        "only": True,
                        "propagate": True,
                    },
                },
            ],
        }

    def test_deny_ace_sets_rights_false(self, action) -> None:
        """Test a D type ACE records its rights as false."""
        acl = action._parse_nfs4_acl("D::EVERYONE@:wa")

        assert acl["entries"] == [
            {"type": "everyone", "write": False, "append": False}
        ]

    def test_no_propagate_flag_clears_propagate(self, action) -> None:
        """Test the n flag turns into propagate false."""
        acl = action._parse_nfs4_acl("A:fdn:jane@example.com:r")

        assert acl["entries"][0]["inheritance"] == {
            "file": True,
            "directory": True,
            "propagate": False,
        }

    def test_inherited_flag_is_promoted_to_entry(self, action) -> None:
        """Test the I flag sets inherited on the entry itself."""
        acl = action._parse_nfs4_acl("A:I:OWNER@:r")

        assert acl["entries"] == [
            {"type": "owner", "read": True, "inherited": True}
        ]

    @pytest.mark.parametrize(
        "perm,expected",
        [
            ("r", {"read": True}),
            ("w", {"write": True}),
            ("a", {"append": True}),
            ("x", {"execute": True}),
            ("d", {"delete": True}),
            ("D", {"delete_child": True}),
            ("o", {"chown": True}),
            ("y", {"synchronize": True}),
            ("t", {"attributes": {"read": True}}),
            ("T", {"attributes": {"write": True}}),
            ("n", {"extended": {"read": True}}),
            ("N", {"extended": {"write": True}}),
            ("c", {"security": {"read": True}}),
            ("C", {"security": {"write": True}}),
        ],
    )
    def test_permission_letters(self, action, perm, expected) -> None:
        """Test each NFS v4 permission letter maps to its field."""
        acl = action._parse_nfs4_acl(f"A::OWNER@:{perm}")

        assert acl["entries"] == [dict({"type": "owner"}, **expected)]

    def test_unknown_permission_letters_are_dropped(self, action) -> None:
        """Test letters outside the permission map are ignored."""
        acl = action._parse_nfs4_acl("A::OWNER@:rZ")

        assert acl["entries"] == [{"type": "owner", "read": True}]

    def test_group_flag_does_not_change_principal_type(self, action) -> None:
        """Test the g flag leaves a named principal typed as a user."""
        acl = action._parse_nfs4_acl("A:g:devs@example.com:r")

        # NFS v4 marks group principals with the g flag, but the
        # parser types every named principal as a user.
        assert acl["entries"][0]["type"] == "user"
        assert acl["entries"][0]["name"] == "devs@example.com"

    def test_bare_principal_is_typed_as_user(self, action) -> None:
        """Test a principal with no domain still parses as a user."""
        acl = action._parse_nfs4_acl("A::nobody:r")

        assert acl["entries"] == [
            {"type": "user", "name": "nobody", "read": True}
        ]

    @pytest.mark.parametrize(
        "text",
        [
            "",
            "# comment only\n",
            "A::OWNER@\n",
            "not an ace\n",
            "A::OWNER@:r:extra\n",
        ],
    )
    def test_empty_or_malformed_input(self, action, text) -> None:
        """Test lines without exactly four fields are skipped."""
        assert action._parse_nfs4_acl(text) == {
            "type": "nfs4",
            "entries": [],
        }
