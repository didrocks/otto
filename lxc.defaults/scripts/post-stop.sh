#!/bin/sh -eux

#
# This script eventually archive all the specific configuration and delta
# from a LXC container run and unmount the necessary items
#

# Copyright © 2013 Canonical Ltd.
# Author: Didier Roche <didier.roche@canonical.com>
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

BASEDIR=$(dirname $LXC_CONFIG_FILE)
RUNDIR=$BASEDIR/run
ARCHIVE=""
POSTSTOP_FLAG=$BASEDIR/.post-stop.done
rm -f "$POSTSTOP_FLAG"

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

archive() {
    ARCHIVEDIR="$BASEDIR/$ARCHIVEDIR"
    mkdir -p "$ARCHIVEDIR"
    previous_dir=$(pwd)
    cd $RUNDIR
    tar -czf "$ARCHIVEDIR/$ISOID.$RUNID.otto" .
    cd $previous_dir
}

unmount_fs() {
    squashfs_dir="$BASEDIR/squashfs"

    umount.aufs $LXC_ROOTFS_PATH || true
    umount $squashfs_dir || true
    umount $ISOMOUNT || true
}

unmount_fs $SQUASHFS

if [ "$ARCHIVE" = "True" ] ; then
    archive
fi
touch "$POSTSTOP_FLAG"
