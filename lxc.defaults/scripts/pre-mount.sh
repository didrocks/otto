#!/bin/sh -eu

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
CACHEDIR=/var/cache/otto
rootfs=$LXC_ROOTFS_PATH
RELEASE=$(distro-info --devel)
ARCH=$(dpkg --print-architecture)
TESTUSER=ubuntu

CUSTOM_INSTALLATION_DIR=""
SQUASHFS_PATH="${CACHEDIR}/filesystem.squashfs"

# TODO: Pass config file in argument
OTTORC=$BASEDIR/scripts/otto.rc
[ -r "$OTTORC" ] && . $OTTORC

prepare_fs() {
    # This function prepares the container with the directories required to
    # expose hardware from the host to the container, mounts the ISO and
    # extracts the squashfs and prepares the overlay used to store the delta
    # 
    # $1: Path to squashfs file
    #
    squashfs_path=$(readlink -f $1)

    if [ ! -r "$squashfs_path" ]; then
        echo "E: File doesn't exist '$squashfs_path'. Exiting!"
        exit 1
    fi

    modprobe aufs

    # delta_dir is the overlay and will contain all the files that have been
    # changed in the container
	delta_dir="$(dirname $LXC_CONFIG_FILE)/delta"
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

prepare_user() {
    # Creates the user in the container and set its privileges
    # $1: Username
    username="$1"
	chroot $rootfs useradd --create-home -s /bin/bash $username || true
    if ! user_exists $username; then
        echo "E: Creation of user '$username' failed. Exiting!"
        exit 1
    fi

 
    # Adds the user to the 'video' group as ACLs will not work in the
    # container on bind-mounted devices
	chroot $rootfs adduser $username video || true
	echo "$username:$username" | chroot $rootfs chpasswd || true
	echo "$username ALL=(ALL) NOPASSWD:ALL" > $rootfs/etc/sudoers.d/$username
}

configure_system() {
    # Configure the last bits of the system: 
    #  - hosts, hostname and networking
    #  - Sources list
    #  - Locale
    #  - Prepares udev
    #  - Disabled whoopsie and enable autologin
    #
    # $1: username
    username=$1
    if ! user_exists $username; then
        echo "E: User '$username' doesn't exist. Exiting!"
        exit 1
    fi

    # Sets hostname 
	hostname=$LXC_NAME
	echo "$hostname" > $rootfs/etc/hostname
	cat <<EOF > $rootfs/etc/hosts
127.0.0.1   localhost
127.0.1.1   $hostname

# The following lines are desirable for IPv6 capable hosts
::1     ip6-localhost ip6-loopback
fe00::0 ip6-localnet
ff00::0 ip6-mcastprefix
ff02::1 ip6-allnodes
ff02::2 ip6-allrouters
EOF

    # Adds custom sources list as universe is not enabled on image by default
	cat <<EOF > $rootfs/etc/apt/sources.list
deb http://archive.ubuntu.com/ubuntu $RELEASE main restricted universe multiverse
deb http://archive.ubuntu.com/ubuntu $RELEASE-updates main restricted universe multiverse
deb http://archive.ubuntu.com/ubuntu $RELEASE-security main restricted universe multiverse
EOF

    # Setup a decent locale
	chroot $rootfs locale-gen en_US.UTF-8
	chroot $rootfs update-locale LANG=en_US.UTF-8

    # Creates an upstart job that copies the content of the host /run/udev to
    # the container /run/udev
	cat <<EOF > $rootfs/etc/init/lxc-udev.conf
start on starting udev and started mounted-run
script
    cp -Ra /var/lxc/udev /run/udev || true
    umount /var/lxc/udev || true
end script
EOF

    # Setup the network interface and disable network-manager
    if ! grep -q "auto eth0"  $rootfs/etc/network/interfaces; then
        cat <<EOF >> $rootfs/etc/network/interfaces

auto eth0
iface eth0 inet dhcp
EOF
    fi

	echo "manual" > $rootfs/etc/init/network-manager.override

    # Disable Whoopsie
    # Apport doesn't work in LXC containers because it does not have access to
    # /proc
    #if [ -r $rootfs/etc/default/whoopsie ]; then
    #    sed -i "s/report_crashes=true/report_crashes=false/" $rootfs/etc/default/whoopsie
    #fi

    # Enable autologin
    if ! grep -q "autologin-user" $rootfs/etc/lightdm/lightdm.conf; then
        echo "autologin-user=$username" >> $rootfs/etc/lightdm/lightdm.conf
    fi
}

test_setup() {
    # Additional steps to prepare the testing environment
    # $1: user
    user=$1

    # rsync default files to the container essentially to install new packages
    if [ -d $BASEDIR/guest/ ]; then
        rsync -avH $BASEDIR/guest/ $rootfs/
    fi

    # rsync custom-installation directory to rootfs
    if [ -d "$CUSTOM_INSTALLATION_DIR/target-override" ]; then
        rsync -avH $CUSTOM_INSTALLATION_DIR/target-override/ $rootfs/
    fi

}

user_exists() {
    # Checks if a user exists
    # $1: Username

    if ! chroot $rootfs getent passwd "$1" 2>/dev/null>/dev/null; then
        return 1
    else
        return 0
    fi
}

prepare_fs $SQUASHFS_PATH
prepare_user $TESTUSER
configure_system $TESTUSER
test_setup $TESTUSER

