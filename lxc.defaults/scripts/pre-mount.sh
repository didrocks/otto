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

BASEDIR=$(dirname $LXC_CONFIG_FILE)
RUNDIR=$BASEDIR/run
rootfs=$LXC_ROOTFS_PATH
TESTUSER=ubuntu

APT_ARCHIVE=""
DISABLE_NETWORK_MANAGER=""
PROXY=""

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

    # $HOME/.local is set to 0600 on the ISO, change it to something useful
    dotlocal=$rootfs/home/$username/.local
    [ ! -d "$dotlocal" ] && mkdir $dotlocal
    chroot $rootfs chown $username:$username /home/$username/.local/
    chmod 0755 $dotlocal
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

    if [ -z "$APT_ARCHIVE" ] ; then
        APT_ARCHIVE="http://archive.ubuntu.com/ubuntu"
    fi

    # Adds custom sources list as universe is not enabled on image by default
    cat <<EOF > $rootfs/etc/apt/sources.list
deb $APT_ARCHIVE $RELEASE main restricted universe multiverse
deb $APT_ARCHIVE $RELEASE-updates main restricted universe multiverse
deb $APT_ARCHIVE $RELEASE-security main restricted universe multiverse
EOF

    # Setup a decent locale
    chroot $rootfs locale-gen en_US.UTF-8
    chroot $rootfs update-locale LANG=en_US.UTF-8

    # Creates an upstart job that copies the content of the host /run/udev to
    # the container /run/udev
    rm -f $rootfs/etc/init/lxc-udev.override
    cat <<EOF > $rootfs/etc/init/lxc-udev.conf
start on starting udev and started mounted-run
script
    cp -Ra /var/lxc/udev /run/udev || true
    umount /var/lxc/udev || true

    echo "manual" > /etc/init/lxc-udev.override
    [ ! -f "/dev/uinput" ] && mknod /dev/uinput c 10 223
end script
EOF

    # Setup the network interface and disable network-manager
    if ! grep -q "auto eth0"  $rootfs/etc/network/interfaces; then
        cat <<EOF >> $rootfs/etc/network/interfaces

auto eth0
iface eth0 inet dhcp
EOF
    fi

    # disable network manager
    if [ "$DISABLE_NETWORK_MANAGER" != "FALSE" ]; then
        echo "manual" > $rootfs/etc/init/network-manager.override
    fi

    # Use optional proxy
    if [ ! -z "$PROXY" ]; then
        cat <<EOF > $rootfs/etc/apt/apt.conf.d/99otto
Acquire::http::proxy "$PROXY";
Acquire::https::proxy "$PROXY";
EOF
        if ! grep -q "http_proxy" $rootfs/etc/environment; then
            echo "http_proxy=$PROXY" >> $rootfs/etc/environment
            echo "https_proxy=$PROXY" >> $rootfs/etc/environment
        fi
    fi

    # Disable Whoopsie
    # Apport doesn't work in LXC containers because it does not have access to
    # /proc
    #if [ -r $rootfs/etc/default/whoopsie ]; then
    #    sed -i "s/report_crashes=true/report_crashes=false/" $rootfs/etc/default/whoopsie
    #fi

    # Enable autologin
    lightdmconf="etc/lightdm/lightdm.conf"
    autologinconf="etc/lightdm/lightdm.conf.d/99-autologin.conf"
    if [ -d "$rootfs/$(dirname $autologinconf)" ]; then
        cat <<EOF >$rootfs/$autologinconf
[SeatDefaults]
autologin-user=ubuntu
EOF
    elif ! grep -q "autologin-user" $rootfs/$lightdmconf; then
        echo "autologin-user=$username" >> $rootfs/$lightdmconf
    else
        cat <<EOF >$rootfs/$lightdmconf
[SeatDefaults]
greeter-session=unity-greeter
autologin-user=ubuntu
EOF
    fi
}

test_setup() {
    # Additional steps to prepare the testing environment
    # $1: user
    user=$1

    # rsync default files to the container essentially to install new packages
    if [ -d $BASEDIR/tools/guest/ ]; then
        rsync -avH $BASEDIR/tools/guest/ $rootfs/
    fi

    # rsync custom-installation directory to rootfs
    if [ -d "$RUNDIR/target-override" ]; then
        rsync -avH $RUNDIR/target-override/ $rootfs/
    fi

    # rsync packages directory to rootfs
    mkdir -p $rootfs/var/local/otto/config/
    if [ -d "$RUNDIR/packages" ]; then
        rsync -avH --no-recursive $RUNDIR/packages/* $rootfs/var/local/otto/config/
        # if specific release config, overwrite with it
        if [ -d "$RUNDIR/packages/$RELEASE" ]; then
            rsync -avH $RUNDIR/packages/$RELEASE/* $rootfs/var/local/otto/config/
        fi
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

prepare_user $TESTUSER
configure_system $TESTUSER
test_setup $TESTUSER
