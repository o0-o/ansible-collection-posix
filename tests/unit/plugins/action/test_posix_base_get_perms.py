# -*- coding: utf-8 -*-
# vim: ts=4:sw=4:sts=4:et:ft=python
#
# Unit tests for _get_perms method in PosixBase

import pytest
from ansible.errors import AnsibleError


@pytest.mark.parametrize("cmd_output, selinux, expected", [
    (
        {
            "rc": 0,
            "stdout_lines": [
                "-rw-r--r-- 1 user group 123 Jul 1 00:00 file"
            ],
            "stdout": ""
        },
        False,
        {
            "mode": "rw-r--r--",
            "owner": "user",
            "group": "group"
        }
    ),
    (
        {
            "rc": 0,
            "stdout_lines": [
                (
                    "user_u:object_r:etc_t:s0 -rw-r--r-- user group 123 Jul "
                    "1 00:00 file"
                )
            ],
            "stdout": ""
        },
        True,
        {
            "mode": "rw-r--r--",
            "owner": "user",
            "group": "group",
            "seuser": "user_u",
            "serole": "object_r",
            "setype": "etc_t",
            "selevel": "s0"
        }
    ),
    (
        {
            "rc": 0,
            "stdout_lines": [
                "-rw-r--r--+ 1 user group 123 Jul 1 00:00 file"
            ],
            "stdout": ""
        },
        False,
        {
            "mode": "rw-r--r--",
            "owner": "user",
            "group": "group"
        }
    )
])
def test_get_perms_valid(base, cmd_output, selinux, expected):
    """
    Verify _get_perms parses POSIX and SELinux output correctly.

    Includes:
    - Basic POSIX mode
    - SELinux context extraction
    - Stripping ACL/attribute symbols
    """
    base._cmd = lambda *args, **kwargs: cmd_output
    result = base._get_perms("/fake/file", selinux=selinux)
    assert result == expected


def test_get_perms_fails_on_error(base):
    """
    Ensure _get_perms raises AnsibleError when ls command fails.
    """
    base._cmd = lambda *args, **kwargs: {
        "rc": 1,
        "stderr": "ls: cannot access"
    }

    with pytest.raises(AnsibleError, match="Could not stat"):
        base._get_perms("/fake/file", selinux=False)


def test_get_perms_raises_on_malformed_selinux_output(base):
    """
    Ensure _get_perms raises if SELinux fields cannot be parsed.
    """
    base._cmd = lambda *args, **kwargs: {
        "rc": 0,
        "stdout": "badselinux -rw-r--r-- user group",
        "stdout_lines": [
            "badselinux -rw-r--r-- user group"
        ]
    }

    with pytest.raises(AnsibleError, match="Unexpected SELinux output"):
        base._get_perms("/fake/file", selinux=True)
