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

BASEDIR=$(dirname $LXC_CONFIG_FILE)
RUNDIR=$BASEDIR/run
rootfs=$LXC_ROOTFS_PATH
TESTUSER=ubuntu
BASEDELTADIR=""
COMMAND=""

# source run specific configuration
CONFIG=$RUNDIR/config
LOCAL_CONFIG=$RUNDIR/config.local
if [ ! -r "$CONFIG" ]; then
    echo "E: No configuration found on $CONFIG. It means you never ran otto start."
    exit 1
fi
. $CONFIG

if [ -r "$LOCAL_CONFIG" ]; then
    . $LOCAL_CONFIG
fi

prepare_fs() {
    # This function prepares the container with the directories required to
    # expose hardware from the host to the container, mounts the ISO and
    # extracts the squashfs and prepares the overlay used to store the delta
    #
    # $1: Path to squashfs file

    IMAGE="$BASDIR/$IMAGE"
    if ! mountpoint -q $ISOMOUNT; then
        echo "I: $ISOMOUNT not mounted yet, creating and mounting"
        mkdir -p $ISOMOUNT
        mount -n -o loop $IMAGE $ISOMOUNT
    fi
    squashfs_path=$(readlink -f $1)

    if [ ! -r "$squashfs_path" ]; then
        echo "E: File doesn't exist '$squashfs_path'. Exiting!"
        exit 1
    fi

    modprobe aufs

    # base delta is an optional base delta parameter from which to upgrade the base system
    # or mount a previous base delta

    # delta_dir is the overlay and will contain all the files that have been
    # changed in the container
    delta_dir="$RUNDIR/delta"
    mkdir -p $delta_dir

    # Mount the squashfs
    squashfs_dir="$(dirname $LXC_CONFIG_FILE)/squashfs"
    mkdir -p $squashfs_dir
    mount -n -o loop,ro $squashfs_path $squashfs_dir

    # FIXME: Overlayfs leaks loop devices
    #mount -n -t overlayfs -o upperdir=$delta_dir,lowerdir=$SQUASHFS_DIR overlayfs $LXC_ROOTFS_PATH
    if [ -z "$BASEDELTADIR" ] ; then
        mount -n -t aufs -o br=$delta_dir=rw:$squashfs_dir=ro aufs $LXC_ROOTFS_PATH
    elif [ "$COMMAND" = "upgrade" ]; then
        BASEDELTADIR="$BASEDIR/$BASEDELTADIR"
        mount -n -t aufs -o br=$BASEDELTADIR=rw:$squashfs_dir=ro aufs $LXC_ROOTFS_PATH
        touch $LXC_ROOTFS_PATH/.upgrade
    else
        BASEDELTADIR="$BASEDIR/$BASEDELTADIR"
        mount -n -t aufs -o br=$delta_dir=rw:br=$BASEDELTADIR=ro:$squashfs_dir=ro aufs $LXC_ROOTFS_PATH
    fi
    umount -l $squashfs_dir

    # Create hardware devices
    mkdir -p $LXC_ROOTFS_PATH/dev/dri $LXC_ROOTFS_PATH/dev/snd $LXC_ROOTFS_PATH/dev/input
    mkdir -p $LXC_ROOTFS_PATH/var/lxc/udev
}

prepare_fs $SQUASHFS
