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
TESTUSER=ubuntu

# source run specific configuration
CONFIG=$RUNDIR/config
if [ ! -r "$CONFIG" ]; then
    echo "E: No configuration found on $CONFIG. It means you never ran otto start."
    exit 1
fi
. $CONFIG


prepare_fs() {
    # This function prepares the container with the directories required to
    # expose hardware from the host to the container, mounts the ISO and
    # extracts the squashfs and prepares the overlay used to store the delta
    #
    # $1: Path to squashfs file
    #
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

    # delta_dir is the overlay and will contain all the files that have been
    # changed in the container
	delta_dir="$RUNDIR/delta"
    # TODO: Make it an option of the start command of otto
	#rm -Rf $delta_dir
	mkdir -p $delta_dir

    # Mount the squashfs
    squashfs_dir="$(dirname $LXC_CONFIG_FILE)/squashfs"
	mkdir -p $squashfs_dir
	mount -n -o loop,ro $squashfs_path $squashfs_dir

    # FIXME: Overlayfs leaks loop devices
	#mount -n -t overlayfs -o upperdir=$delta_dir,lowerdir=$SQUASHFS_DIR overlayfs $LXC_ROOTFS_PATH
	mount -n -t aufs -o br=$delta_dir=rw:$squashfs_dir=ro aufs $LXC_ROOTFS_PATH
	umount -l $squashfs_dir

	# Create hardware devices
	mkdir -p $LXC_ROOTFS_PATH/dev/dri $LXC_ROOTFS_PATH/dev/snd $LXC_ROOTFS_PATH/dev/input
	mkdir -p $LXC_ROOTFS_PATH/var/lxc/udev
}

prepare_fs $SQUASHFS
