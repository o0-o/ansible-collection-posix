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

"""Unit tests for the fstab filter plugin."""

from __future__ import annotations

from typing import Any, Dict, List, Union

import pytest

from ansible_collections.o0_o.posix.plugins.filter.fstab import FilterModule


@pytest.fixture
def filter_module() -> FilterModule:
    """Create FilterModule instance for testing."""
    return FilterModule()


def test_fstab_basic(filter_module: FilterModule) -> None:
    """Test basic fstab parsing."""
    # Test with string input
    fstab_content = """/dev/sda1   /       ext4    defaults        0   1
/dev/sda2   /home   ext4    defaults,noatime   0   2"""

    result = filter_module.fstab(fstab_content)

    # Check the normalized output
    expected = [
        {
            "source": "/dev/sda1",
            "mount": "/",
            "type": "ext4",
            "options": [{"defaults": True}],
            "dump": 0,
            "pass": 1,
        },
        {
            "source": "/dev/sda2",
            "mount": "/home",
            "type": "ext4",
            "options": [{"defaults": True}, {"noatime": True}],
            "dump": 0,
            "pass": 2,
        },
    ]
    assert result == expected


def test_fstab_with_complex_options(filter_module: FilterModule) -> None:
    """Test fstab parsing with complex mount options."""
    fstab_content = """/dev/sda1   /       ext4    defaults        0   1
UUID=abc123   /boot   ext2    defaults,ro   1   2
tmpfs   /tmp   tmpfs    defaults,nodev,nosuid   0   0"""

    result = filter_module.fstab(fstab_content)

    expected = [
        {
            "source": "/dev/sda1",
            "mount": "/",
            "type": "ext4",
            "options": [{"defaults": True}],
            "dump": 0,
            "pass": 1,
        },
        {
            "source": "UUID=abc123",
            "mount": "/boot",
            "type": "ext2",
            "options": [{"defaults": True}, {"ro": True}],
            "dump": 1,
            "pass": 2,
        },
        {
            "source": "tmpfs",
            "mount": "/tmp",
            "type": "tmpfs",
            "options": [{"defaults": True}, {"nodev": True}, {"nosuid": True}],
            "dump": 0,
            "pass": 0,
        },
    ]

    assert result == expected


def test_fstab_with_comments_and_blank_lines(
    filter_module: FilterModule,
) -> None:
    """Test fstab parsing with comments and blank lines."""
    fstab_content = """# /etc/fstab: static file system information
#
# <file system> <mount point>   <type>  <options>       <dump>  <pass>

/dev/sda1       /               ext4    defaults        0       1

# This is a comment
"""
    result = filter_module.fstab(fstab_content)

    expected = [
        {
            "source": "/dev/sda1",
            "mount": "/",
            "type": "ext4",
            "options": [{"defaults": True}],
            "dump": 0,
            "pass": 1,
        }
    ]
    assert result == expected


def test_fstab_with_nfs(filter_module: FilterModule) -> None:
    """Test fstab parsing with NFS entries."""
    fstab_content = """/dev/sda1   /   ext4   defaults,noatime   0   1
nfs-server:/export   /mnt/nfs   nfs   rw,hard,intr   0   0"""

    result = filter_module.fstab(fstab_content)

    expected = [
        {
            "source": "/dev/sda1",
            "mount": "/",
            "type": "ext4",
            "options": [{"defaults": True}, {"noatime": True}],
            "dump": 0,
            "pass": 1,
        },
        {
            "source": "nfs-server:/export",
            "mount": "/mnt/nfs",
            "type": "nfs",
            "options": [{"rw": True}, {"hard": True}, {"intr": True}],
            "dump": 0,
            "pass": 0,
        },
    ]

    assert result == expected


def test_fstab_with_swap(filter_module: FilterModule) -> None:
    """Test fstab parsing with swap entries."""
    fstab_content = "/dev/sda3   none   swap   sw   0   0"

    result = filter_module.fstab(fstab_content)

    expected = [
        {
            "source": "/dev/sda3",
            "mount": None,  # "none" is converted to None
            "type": "swap",
            "options": [{"sw": True}],
            "dump": 0,
            "pass": 0,
        }
    ]

    assert result == expected


def test_fstab_with_bind_mount(filter_module: FilterModule) -> None:
    """Test fstab parsing with bind mount entries."""
    fstab_content = "/olddir   /newdir   none   bind   0   0"

    result = filter_module.fstab(fstab_content)

    expected = [
        {
            "source": "/olddir",
            "mount": "/newdir",
            "type": "none",
            "options": [{"bind": True}],
            "dump": 0,
            "pass": 0,
        }
    ]

    assert result == expected


def test_fstab_with_invalid_dump_pass_values(
    filter_module: FilterModule,
) -> None:
    """Test fstab parsing with invalid dump/pass values."""
    # JC will parse numeric values correctly, so test with actual
    # negative values
    fstab_content = """/dev/sda1   /   ext4   defaults   -1   -1
/dev/sda2   /home   ext4   defaults   auto   auto"""

    result = filter_module.fstab(fstab_content)

    expected = [
        {
            "source": "/dev/sda1",
            "mount": "/",
            "type": "ext4",
            "options": [{"defaults": True}],
            "dump": -1,
            "pass": -1,
        },
        {
            "source": "/dev/sda2",
            "mount": "/home",
            "type": "ext4",
            "options": [{"defaults": True}],
            "dump": None,  # Non-integer becomes None
            "pass": None,  # Non-integer becomes None
        },
    ]

    assert result == expected


@pytest.mark.parametrize(
    "input_type,input_data",
    [
        ("string", "/dev/sda1\t/\text4\tdefaults\t0\t1"),
        (
            "dict",
            {
                "stdout": "/dev/sda1\t/\text4\tdefaults\t0\t1",
                "rc": 0,
            },
        ),
    ],
)
def test_fstab_input_types(
    filter_module: FilterModule,
    input_type: str,
    input_data: Union[str, Dict[str, Any]],
) -> None:
    """Test fstab filter with different input types."""
    result = filter_module.fstab(input_data)

    # Result should be normalized
    expected = [
        {
            "source": "/dev/sda1",
            "mount": "/",
            "type": "ext4",
            "options": [{"defaults": True}],
            "dump": 0,
            "pass": 1,
        }
    ]
    assert result == expected


def test_fstab_empty_input(filter_module: FilterModule) -> None:
    """Test fstab filter with empty input."""
    result = filter_module.fstab("")
    assert result == []


def test_fstab_with_fuse_filesystem(filter_module: FilterModule) -> None:
    """Test fstab parsing with FUSE filesystems."""
    fstab_content = (
        "sshfs#user@host:/path   /mnt/ssh   fuse.sshfs   defaults   0   0\n"
        "encfs#/encrypted   /decrypted   fuse.encfs   defaults   0   0"
    )

    result = filter_module.fstab(fstab_content)

    expected = [
        {
            "source": "sshfs#user@host:/path",
            "mount": "/mnt/ssh",
            "type": "fuse.sshfs",
            "options": [{"defaults": True}],
            "dump": 0,
            "pass": 0,
        },
        {
            "source": "encfs#/encrypted",
            "mount": "/decrypted",
            "type": "fuse.encfs",
            "options": [{"defaults": True}],
            "dump": 0,
            "pass": 0,
        },
    ]

    assert result == expected


def test_fstab_generation_basic(filter_module: FilterModule) -> None:
    """Test generating fstab content from structured data."""
    entries = [
        {
            "source": "/dev/sda1",
            "mount": "/",
            "type": "ext4",
            "options": [{"defaults": True}, {"noatime": True}],
            "dump": 0,
            "pass": 1,
        },
        {
            "source": "/dev/sda2",
            "mount": "/home",
            "type": "ext4",
            "options": [{"defaults": True}],
            "dump": 0,
            "pass": 2,
        },
    ]

    result = filter_module.fstab(entries)

    expected_lines = [
        "/dev/sda1\t/\text4\tdefaults,noatime\t0\t1",
        "/dev/sda2\t/home\text4\tdefaults\t0\t2",
    ]

    # Split result into lines and compare (ignoring empty lines)
    result_lines = [line for line in result.strip().split("\n") if line]
    assert result_lines == expected_lines


def test_fstab_generation_multiple_types(filter_module: FilterModule) -> None:
    """Test generating fstab with multiple filesystem types."""
    entries = [
        # Regular filesystem
        {
            "source": "/dev/sda1",
            "mount": "/",
            "type": "ext4",
            "options": [{"defaults": True}, {"noatime": True}],
            "dump": 0,
            "pass": 1,
        },
        # UUID-based mount
        {
            "source": "UUID=abc-123",
            "mount": "/boot",
            "type": "ext2",
            "options": [{"defaults": True}, {"ro": True}],
            "dump": 1,
            "pass": 2,
        },
        # Virtual filesystem (tmpfs)
        {
            "source": "tmpfs",
            "mount": "/tmp",
            "type": "tmpfs",
            "options": [
                {"defaults": True},
                {"nodev": True},
                {"nosuid": True},
                {"size": "2G"},
            ],
            "dump": 0,
            "pass": 0,
        },
        # Pseudo filesystem (proc)
        {
            "source": "proc",
            "mount": "/proc",
            "type": "proc",
            "options": [{"defaults": True}],
            "dump": 0,
            "pass": 0,
        },
        # Swap
        {
            "source": "/dev/sda3",
            "mount": None,  # Use None for swap
            "type": "swap",
            "options": [{"sw": True}],
            "dump": 0,
            "pass": 0,
        },
        # Network filesystem (NFS)
        {
            "source": "nfs-server:/export",
            "mount": "/mnt/nfs",
            "type": "nfs",
            "options": [{"rw": True}, {"hard": True}, {"intr": True}],
            "dump": 0,
            "pass": 0,
        },
        # Network filesystem (CIFS/SMB)
        {
            "source": "//smb-server/share",
            "mount": "/mnt/smb",
            "type": "cifs",
            "options": [
                {"username": "user"},
                {"password": "pass"},
                {"domain": "WORKGROUP"},
            ],
            "dump": 0,
            "pass": 0,
        },
        # Bind mount
        {
            "source": "/olddir",
            "mount": "/newdir",
            "type": "none",
            "options": [{"bind": True}],
            "dump": 0,
            "pass": 0,
        },
        # FUSE filesystem
        {
            "source": "sshfs#user@host:/path",
            "mount": "/mnt/ssh",
            "type": "fuse.sshfs",
            "options": [{"defaults": True}, {"reconnect": True}],
            "dump": 0,
            "pass": 0,
        },
        # Overlay filesystem
        {
            "source": "overlay",
            "mount": "/var/docker",
            "type": "overlay",
            "options": [
                {"lowerdir": "/lower"},
                {"upperdir": "/upper"},
                {"workdir": "/work"},
            ],
            "dump": 0,
            "pass": 0,
        },
    ]

    result = filter_module.fstab(entries)

    expected_lines = [
        "/dev/sda1\t/\text4\tdefaults,noatime\t0\t1",
        "UUID=abc-123\t/boot\text2\tdefaults,ro\t1\t2",
        "tmpfs\t/tmp\ttmpfs\tdefaults,nodev,nosuid,size=2G\t0\t0",
        "proc\t/proc\tproc\tdefaults\t0\t0",
        "/dev/sda3\tnone\tswap\tsw\t0\t0",
        "nfs-server:/export\t/mnt/nfs\tnfs\trw,hard,intr\t0\t0",
        (
            "//smb-server/share\t/mnt/smb\tcifs\t"
            "username=user,password=pass,domain=WORKGROUP\t0\t0"
        ),
        "/olddir\t/newdir\tnone\tbind\t0\t0",
        (
            "sshfs#user@host:/path\t/mnt/ssh\tfuse.sshfs\t"
            "defaults,reconnect\t0\t0"
        ),
        (
            "overlay\t/var/docker\toverlay\t"
            "lowerdir=/lower,upperdir=/upper,workdir=/work\t0\t0"
        ),
    ]

    result_lines = [line for line in result.strip().split("\n") if line]
    assert result_lines == expected_lines


def test_fstab_generation_with_options(filter_module: FilterModule) -> None:
    """Test generating fstab with complex mount options."""
    entries = [
        {
            "source": "UUID=abc-123",
            "mount": "/boot",
            "type": "ext2",
            "options": [{"defaults": True}, {"ro": True}],
            "dump": 1,
            "pass": 2,
        },
        {
            "source": "tmpfs",
            "mount": "/tmp",
            "type": "tmpfs",
            "options": [
                {"defaults": True},
                {"nodev": True},
                {"nosuid": True},
                {"size": "2G"},
            ],
            "dump": 0,
            "pass": 0,
        },
    ]

    result = filter_module.fstab(entries)

    expected_lines = [
        "UUID=abc-123\t/boot\text2\tdefaults,ro\t1\t2",
        "tmpfs\t/tmp\ttmpfs\tdefaults,nodev,nosuid,size=2G\t0\t0",
    ]

    result_lines = [line for line in result.strip().split("\n") if line]
    assert result_lines == expected_lines


def test_fstab_generation_swap(filter_module: FilterModule) -> None:
    """Test generating fstab entry for swap."""
    entries = [
        {
            "source": "/dev/sda3",
            "mount": None,  # None should become "none" in output
            "type": "swap",
            "options": [{"sw": True}],
            "dump": 0,
            "pass": 0,
        }
    ]

    result = filter_module.fstab(entries)

    expected = "/dev/sda3\tnone\tswap\tsw\t0\t0\n"
    assert result == expected


def test_fstab_generation_nfs(filter_module: FilterModule) -> None:
    """Test generating fstab entry for NFS."""
    entries = [
        {
            "source": "nfs-server:/export",
            "mount": "/mnt/nfs",
            "type": "nfs",
            "options": [{"rw": True}, {"hard": True}, {"intr": True}],
            "dump": 0,
            "pass": 0,
        }
    ]

    result = filter_module.fstab(entries)

    expected = "nfs-server:/export\t/mnt/nfs\tnfs\trw,hard,intr\t0\t0\n"
    assert result == expected


def test_fstab_generation_empty_list(filter_module: FilterModule) -> None:
    """Test generating fstab from empty list."""
    # Use generate_fstab directly since fstab() no longer accepts empty lists
    from ansible_collections.o0_o.posix.plugins.module_utils import generate_fstab
    result = generate_fstab([])
    assert result == ""  # Empty list generates empty string


def test_fstab_generation_single_entry(filter_module: FilterModule) -> None:
    """Test generating fstab from single entry dict."""
    single_entry = {
        "source": "/dev/sda1",
        "mount": "/",
        "type": "ext4",
        "options": [{"defaults": True}],
        "dump": 0,
        "pass": 1,
    }

    result = filter_module.fstab(single_entry)

    expected = "/dev/sda1\t/\text4\tdefaults\t0\t1\n"
    assert result == expected


def test_fstab_generation_with_defaults(filter_module: FilterModule) -> None:
    """Test generating fstab with missing optional fields."""
    entries = [
        {
            "source": "/dev/sda1",
            "mount": "/",
            # type defaults to "auto"
            # options defaults to "defaults"
            # dump defaults to 0
            # pass defaults to 1 for root
        }
    ]

    result = filter_module.fstab(entries)

    # type=auto, pass=1 for root, defaults for options
    expected = "/dev/sda1\t/\tauto\tdefaults\t0\t1\n"
    assert result == expected


def test_fstab_generation_intelligent_defaults(
    filter_module: FilterModule,
) -> None:
    """Test intelligent defaults for pass values based on mount/type."""
    entries = [
        {
            "source": "/dev/sda1",
            "mount": "/",
            "type": "ext4",
            # No pass specified - should default to 1 for root
        },
        {
            "source": "/dev/sda2",
            "mount": "/home",
            "type": "ext4",
            # No pass specified - should default to 2 for regular fs
        },
        {
            "source": "tmpfs",
            "mount": "/tmp",
            "type": "tmpfs",
            # No pass specified - should default to 0 for tmpfs
        },
        {
            "source": "/dev/sda3",
            "mount": None,
            "type": "swap",
            # No pass specified - should default to 0 for swap
        },
        {
            "source": "nfs-server:/export",
            "mount": "/mnt/nfs",
            "type": "nfs",
            # No pass specified - should default to 0 for network fs
        },
        {
            "source": "sshfs#user@host:/",
            "mount": "/mnt/ssh",
            "type": "fuse.sshfs",
            # No pass specified - should default to 0 for FUSE
        },
    ]

    result = filter_module.fstab(entries)

    expected_lines = [
        "/dev/sda1\t/\text4\tdefaults\t0\t1",  # root gets pass=1
        "/dev/sda2\t/home\text4\tdefaults\t0\t2",  # regular fs: pass=2
        "tmpfs\t/tmp\ttmpfs\tdefaults\t0\t0",  # tmpfs gets pass=0
        "/dev/sda3\tnone\tswap\tdefaults\t0\t0",  # swap gets pass=0
        (
            "nfs-server:/export\t/mnt/nfs\tnfs\tdefaults\t0\t0"
        ),  # network fs gets pass=0
        (
            "sshfs#user@host:/\t/mnt/ssh\tfuse.sshfs\tdefaults\t0\t0"
        ),  # FUSE gets pass=0
    ]

    result_lines = [line for line in result.strip().split("\n") if line]
    assert result_lines == expected_lines


def test_fstab_bidirectional_conversion(filter_module: FilterModule) -> None:
    """Test parsing fstab and then generating it back."""
    # Parse the content
    fstab_content = "/dev/sda1\t/\text4\tdefaults,noatime\t0\t1"
    parsed = filter_module.fstab(fstab_content)

    # Generate it back
    regenerated = filter_module.fstab(parsed)

    expected = "/dev/sda1\t/\text4\tdefaults,noatime\t0\t1\n"
    assert regenerated == expected


def test_fstab_base64_content(filter_module: FilterModule) -> None:
    """Test parsing base64 encoded fstab content from slurp module."""
    import base64

    # Original fstab content
    fstab_content = (
        "/dev/sda1\t/\text4\tdefaults\t0\t1\n"
        "/dev/sda2\t/home\text4\tdefaults,noatime\t0\t2"
    )

    # Encode to base64
    encoded_content = base64.b64encode(fstab_content.encode()).decode()

    # Create dict with 'content' key (like slurp module)
    slurp_result = {
        "content": encoded_content,
        "encoding": "base64",
        "source": "/etc/fstab",
    }

    result = filter_module.fstab(slurp_result)

    expected = [
        {
            "source": "/dev/sda1",
            "mount": "/",
            "type": "ext4",
            "options": [{"defaults": True}],
            "dump": 0,
            "pass": 1,
        },
        {
            "source": "/dev/sda2",
            "mount": "/home",
            "type": "ext4",
            "options": [{"defaults": True}, {"noatime": True}],
            "dump": 0,
            "pass": 2,
        },
    ]

    assert result == expected


def test_fstab_non_base64_content_key(filter_module: FilterModule) -> None:
    """Test that non-base64 content in 'content' key still works."""
    # Plain text content in dict with 'content' key
    plain_result = {
        "content": "/dev/sda1\t/\text4\tdefaults\t0\t1",
        "source": "/etc/fstab",
    }

    result = filter_module.fstab(plain_result)

    expected = [
        {
            "source": "/dev/sda1",
            "mount": "/",
            "type": "ext4",
            "options": [{"defaults": True}],
            "dump": 0,
            "pass": 1,
        }
    ]

    assert result == expected


def test_fstab_invalid_base64_content(filter_module: FilterModule) -> None:
    """Test that invalid base64 content raises appropriate error."""
    from ansible.errors import AnsibleFilterError

    # Invalid base64 that looks like base64 but isn't
    invalid_result = {
        "content": "not-valid-base64!@#$%^&*()",
        "encoding": "base64",
        "source": "/etc/fstab",
    }

    # This should raise an error because it's not valid fstab content
    with pytest.raises(AnsibleFilterError) as exc_info:
        filter_module.fstab(invalid_result)

    assert "Error processing fstab" in str(exc_info.value)


def test_fstab_base64_with_comments(filter_module: FilterModule) -> None:
    """Test parsing base64 encoded fstab with comments and blanks."""
    import base64

    # Original fstab content with comments
    fstab_content = """# /etc/fstab: static file system information
#
# <file system> <mount point>   <type>  <options>       <dump>  <pass>

/dev/sda1       /               ext4    defaults        0       1

# This is a comment
/dev/sda2       /home           ext4    defaults,noatime        0       2
"""

    # Encode to base64
    encoded_content = base64.b64encode(fstab_content.encode()).decode()

    # Create dict with 'content' key
    slurp_result = {"content": encoded_content, "encoding": "base64"}

    result = filter_module.fstab(slurp_result)

    expected = [
        {
            "source": "/dev/sda1",
            "mount": "/",
            "type": "ext4",
            "options": [{"defaults": True}],
            "dump": 0,
            "pass": 1,
        },
        {
            "source": "/dev/sda2",
            "mount": "/home",
            "type": "ext4",
            "options": [{"defaults": True}, {"noatime": True}],
            "dump": 0,
            "pass": 2,
        },
    ]

    assert result == expected


def test_fstab_base64_empty_content(filter_module: FilterModule) -> None:
    """Test parsing base64 encoded empty fstab."""
    import base64

    # Empty content
    empty_content = ""

    # Encode to base64
    encoded_content = base64.b64encode(empty_content.encode()).decode()

    # Create dict with 'content' key
    slurp_result = {"content": encoded_content, "encoding": "base64"}

    result = filter_module.fstab(slurp_result)

    assert result == []


def test_fstab_stdout_vs_content_keys(filter_module: FilterModule) -> None:
    """Test different behavior for stdout vs content keys."""
    fstab_text = "/dev/sda1\t/\text4\tdefaults\t0\t1"

    # Test with stdout key (no base64 detection)
    stdout_result = {"stdout": fstab_text, "rc": 0}

    result_stdout = filter_module.fstab(stdout_result)

    # Test with content key (base64 detection enabled)
    content_result = {"content": fstab_text}

    result_content = filter_module.fstab(content_result)

    # Both should parse correctly
    expected = [
        {
            "source": "/dev/sda1",
            "mount": "/",
            "type": "ext4",
            "options": [{"defaults": True}],
            "dump": 0,
            "pass": 1,
        }
    ]

    assert result_stdout == expected
    assert result_content == expected
