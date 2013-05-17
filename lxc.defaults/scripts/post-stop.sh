#!/bin/sh -eux

#
# This script prepares an LXC container from an ISO image and setup an overlay
# to run tests on it.
#

# Copyright © 2013 Canonical Ltd.
# Author: Jean-baptiste Lallement <jean-baptiste.lallement@canonical.com>
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 2, as
# published by the Free Software Foundation.

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License along
# with this program; if not, write to the Free Software Foundation, Inc.,
# 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.
#

# TODO:
# - Add an option to keep an exsting delta
# - Add an option to restore from an existing delta

BASEDIR=$(dirname $LXC_CONFIG_FILE)
RUNDIR=$BASEDIR/run
rootfs=$LXC_ROOTFS_PATH
RELEASE=$(distro-info --devel)
ARCH=$(dpkg --print-architecture)
TESTUSER=ubuntu

# source run specific configuration
CONFIG=$RUNDIR/config
if [ ! -r "$CONFIG" ]; then
    echo "E: No configuration found on $CONFIG. It means you never ran otto start."
    exit 1
fi
. $CONFIG

unmount_fs() {
    iso_mount="/run/otto/iso/$(echo $IMAGE | tr '/' '_')"
    squashfs_dir="$(dirname $LXC_CONFIG_FILE)/squashfs"

    umount.aufs $LXC_ROOTFS_PATH || true
    umount $squashfs_dir || true 
    umount $iso_mount || true
}
unmount_fs $SQUASHFS
