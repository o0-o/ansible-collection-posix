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

"""Storage driver definitions and classifications."""

from __future__ import annotations

STORAGE_DRIVERS = {
    # Regular filesystem drivers (typically backed by block devices)
    "ext2": {"class": "filesystem", "type": "regular"},
    "ext3": {"class": "filesystem", "type": "regular"},
    "ext4": {"class": "filesystem", "type": "regular"},
    "xfs": {"class": "filesystem", "type": "regular"},
    "apfs": {"class": "filesystem", "type": "regular"},
    "ufs": {"class": "filesystem", "type": "regular"},
    "ffs": {"class": "filesystem", "type": "regular"},
    "hfs": {"class": "filesystem", "type": "regular"},
    "hfsplus": {"class": "filesystem", "type": "regular"},
    "jfs": {"class": "filesystem", "type": "regular"},
    "reiserfs": {"class": "filesystem", "type": "regular"},
    "f2fs": {"class": "filesystem", "type": "regular"},
    "nilfs2": {"class": "filesystem", "type": "regular"},
    "ocfs2": {"class": "filesystem", "type": "regular"},
    "gfs2": {"class": "filesystem", "type": "regular"},
    "vfat": {"class": "filesystem", "type": "regular"},
    "msdos": {"class": "filesystem", "type": "regular"},
    "exfat": {"class": "filesystem", "type": "regular"},
    "ntfs": {"class": "filesystem", "type": "regular"},
    "ntfs3": {"class": "filesystem", "type": "regular"},
    "bcachefs": {"class": "filesystem", "type": "regular"},
    "iso9660": {"class": "filesystem", "type": "regular"},
    "udf": {"class": "filesystem", "type": "regular"},
    "squashfs": {"class": "filesystem", "type": "regular"},
    "erofs": {"class": "filesystem", "type": "regular"},

    # Virtual filesystems
    # Kernel API / interface filesystems
    "proc": {"class": "filesystem", "type": "virtual", "source": "kernel"},
    "procfs": {"class": "filesystem", "type": "virtual", "source": "kernel"},
    "sysfs": {"class": "filesystem", "type": "virtual", "source": "kernel"},
    "devfs": {"class": "filesystem", "type": "virtual", "source": "kernel"},
    "devpts": {"class": "filesystem", "type": "virtual", "source": "kernel"},
    "devtmpfs": {"class": "filesystem", "type": "virtual", "source": "kernel"},
    "debugfs": {"class": "filesystem", "type": "virtual", "source": "kernel"},
    "securityfs": {"class": "filesystem", "type": "virtual", "source": "kernel"},
    "selinuxfs": {"class": "filesystem", "type": "virtual", "source": "kernel"},
    "cgroup": {"class": "filesystem", "type": "virtual", "source": "kernel"},
    "cgroup2": {"class": "filesystem", "type": "virtual", "source": "kernel"},
    "pstore": {"class": "filesystem", "type": "virtual", "source": "kernel"},
    "efivarfs": {"class": "filesystem", "type": "virtual", "source": "kernel"},
    "configfs": {"class": "filesystem", "type": "virtual", "source": "kernel"},
    "hugetlbfs": {"class": "filesystem", "type": "virtual", "source": "kernel"},
    "mqueue": {"class": "filesystem", "type": "virtual", "source": "kernel"},
    "bpf": {"class": "filesystem", "type": "virtual", "source": "kernel"},
    "tracefs": {"class": "filesystem", "type": "virtual", "source": "kernel"},
    "binfmt_misc": {"class": "filesystem", "type": "virtual", "source": "kernel"},
    "rpc_pipefs": {"class": "filesystem", "type": "virtual", "source": "kernel"},
    "nsfs": {"class": "filesystem", "type": "virtual", "source": "kernel"},
    "nfsd": {"class": "filesystem", "type": "virtual", "source": "kernel"},
    "fdescfs": {"class": "filesystem", "type": "virtual", "source": "kernel"},

    # Memory-backed filesystems
    "tmpfs": {"class": "filesystem", "type": "virtual", "source": "memory"},
    "ramfs": {"class": "filesystem", "type": "virtual", "source": "memory"},

    # Automounter
    "autofs": {"class": "filesystem", "type": "virtual"},

    # Host/guest integration
    "vboxsf": {"class": "filesystem", "type": "virtual", "source": "hypervisor"},
    "vmhgfs": {"class": "filesystem", "type": "virtual", "source": "hypervisor"},

    # Overlay filesystem drivers (views/unions/transforms of other filesystems)
    # Union / Merge filesystems
    "overlay": {"class": "filesystem", "type": "overlay"},
    "overlayfs": {"class": "filesystem", "type": "overlay"},
    "aufs": {"class": "filesystem", "type": "overlay"},
    "unionfs": {"class": "filesystem", "type": "overlay"},
    "unionfs-fuse": {"class": "filesystem", "type": "overlay", "driver": {"fuse": {"type": "unionfs"}}},
    "fuse.unionfs": {"class": "filesystem", "type": "overlay", "driver": {"fuse": {"type": "unionfs"}}},
    "mergerfs": {"class": "filesystem", "type": "overlay", "driver": {"fuse": {"type": "mergerfs"}}},
    "fuse.mergerfs": {"class": "filesystem", "type": "overlay", "driver": {"fuse": {"type": "mergerfs"}}},
    "mhddfs": {"class": "filesystem", "type": "overlay", "driver": {"fuse": {"type": "mhddfs"}}},
    "fuse.mhddfs": {"class": "filesystem", "type": "overlay", "driver": {"fuse": {"type": "mhddfs"}}},
    # Transform / Re-mapping filesystems
    "bindfs": {"class": "filesystem", "type": "overlay", "driver": {"fuse": {"type": "bindfs"}}},
    "fuse.bindfs": {"class": "filesystem", "type": "overlay", "driver": {"fuse": {"type": "bindfs"}}},
    "nullfs": {"class": "filesystem", "type": "overlay"},
    "encfs": {"class": "filesystem", "type": "overlay", "driver": {"fuse": {"type": "encfs"}}},
    "fuse.encfs": {"class": "filesystem", "type": "overlay", "driver": {"fuse": {"type": "encfs"}}},
    "gocryptfs": {"class": "filesystem", "type": "overlay", "driver": {"fuse": {"type": "gocryptfs"}}},
    "fuse.gocryptfs": {"class": "filesystem", "type": "overlay", "driver": {"fuse": {"type": "gocryptfs"}}},
    "cryfs": {"class": "filesystem", "type": "overlay", "driver": {"fuse": {"type": "cryfs"}}},
    "fuse.cryfs": {"class": "filesystem", "type": "overlay", "driver": {"fuse": {"type": "cryfs"}}},
    "ecryptfs": {"class": "filesystem", "type": "overlay"},
    "fusecompress": {"class": "filesystem", "type": "overlay", "driver": {"fuse": {"type": "fusecompress"}}},
    "fuse.fusecompress": {"class": "filesystem", "type": "overlay", "driver": {"fuse": {"type": "fusecompress"}}},
    "compfused": {"class": "filesystem", "type": "overlay", "driver": {"fuse": {"type": "compfused"}}},
    "fuse.compfused": {"class": "filesystem", "type": "overlay", "driver": {"fuse": {"type": "compfused"}}},
    # Isolation / Container-specific
    "lxcfs": {"class": "filesystem", "type": "overlay", "driver": {"fuse": {"type": "lxcfs"}}},
    "fuse.lxcfs": {"class": "filesystem", "type": "overlay", "driver": {"fuse": {"type": "lxcfs"}}},
    "shiftfs": {"class": "filesystem", "type": "overlay"},
    # Snapshot / Copy-on-Write
    "translucentfs": {"class": "filesystem", "type": "overlay", "driver": {"fuse": {"type": "translucentfs"}}},
    "fuse.translucentfs": {"class": "filesystem", "type": "overlay", "driver": {"fuse": {"type": "translucentfs"}}},

    # Network filesystem drivers
    "nfs": {"class": "filesystem", "type": "network"},
    "nfs4": {"class": "filesystem", "type": "network"},
    "smbfs": {"class": "filesystem", "type": "network"},
    "cifs": {"class": "filesystem", "type": "network"},
    "afs": {"class": "filesystem", "type": "network"},
    "coda": {"class": "filesystem", "type": "network"},
    "ncpfs": {"class": "filesystem", "type": "network"},
    "sshfs": {"class": "filesystem", "type": "network", "driver": {"fuse": {"type": "sshfs"}}},
    "fuse.sshfs": {"class": "filesystem", "type": "network", "driver": {"fuse": {"type": "sshfs"}}},
    "glusterfs": {"class": "filesystem", "type": "network"},
    "ceph": {"class": "filesystem", "type": "network"},
    "9p": {"class": "filesystem", "type": "network"},  # virtfs
    "smb3": {"class": "filesystem", "type": "network"},
    "lustre": {"class": "filesystem", "type": "network"},
    "orangefs": {"class": "filesystem", "type": "network"},
    "pmxfs": {"class": "filesystem", "type": "network"},

    # FUSE NTFS (kernel-backed is 'ntfs' or 'ntfs3')
    "ntfs-3g": {
        "class": "filesystem",
        "type": "regular",
        "driver": {
            "fuse": {
                "type": "ntfs3-g",
            }
        }
    },

    # Fuse drivers
    "fuse": {"class": "filesystem", "type": "fuse"},
    "osxfuse": {"class": "filesystem", "type": "fuse"},  # macOS FUSE type name on some versions
    "osxfusefs": {"class": "filesystem", "type": "fuse"},  # older macOS FUSE
    "macfuse": {"class": "filesystem", "type": "fuse"},  # newer macOS FUSE

    # Ambiguous drivers (could be filesystem or volume manager)
    "zfs": {},
    "btrfs": {},
    "dm": {},
    "md": {},
}
