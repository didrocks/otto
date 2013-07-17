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

echo "I: Running preparation script: $0 $@"

BASEDIR=$(dirname $(readlink -f $0))
TESTUSER=phablet

APT_ARCHIVE="http://ports.ubuntu.com/ubuntu-ports/"
DISABLE_NETWORK_MANAGER=""
PROXY=""

if [ $# -eq 0 ]; then
    echo "E: testname missing. Exiting!"
    exit 1
fi
TESTNAME=$1
TESTDIR=$BASEDIR/$TESTNAME
if [ ! -d "$TESTDIR" ]; then
    echo "E: Directory not found or is not a directory: $TESTDIR . Exiting!"
    exit 1
fi

# source run specific configuration
CONFIG=$BASEDIR/config
if [ -r "$CONFIG" ]; then
    . $CONFIG
fi


prepare_user() {
    # Creates the user in the container and set its privileges
    #
    # This function checks that the test user exists and creates it if it does
    # not. It also adds it to sudoers without password and adds the ssh keys
    #
    # Args:
    #   $1: Username
    username="$1"
    echo "I: Configuring user $username"
    useradd --create-home -s /bin/bash $username || true
    if ! user_exists $username; then
        echo "E: Creation of user '$username' failed. Exiting!"
        exit 1
    fi

    echo "$username:$username" | chpasswd || true
    echo "$username ALL=(ALL) NOPASSWD:ALL" > /etc/sudoers.d/$username

    # TODO Adds ssh keys
}

configure_system() {
    # Various configuration steps
    #
    # Configure the last bits of the system:
    #  - Sources list
    #  - Locale
    #
    # Args:
    #   $1: username
    echo "I: Configuring system"
    username=$1
    if ! user_exists $username; then
        echo "E: User '$username' doesn't exist. Exiting!"
        exit 1
    fi

    if [ -z "$APT_ARCHIVE" ] ; then
        APT_ARCHIVE="http://ports.ubuntu.com/ubuntu-ports/"
    fi

    # Adds custom sources list as universe is not enabled on image by default
    cat <<EOF > /etc/apt/sources.list
deb $APT_ARCHIVE $RELEASE main restricted universe multiverse
deb $APT_ARCHIVE $RELEASE-updates main restricted universe multiverse
deb $APT_ARCHIVE $RELEASE-security main restricted universe multiverse
EOF

    # Setup a decent locale
    locale-gen en_US.UTF-8
    update-locale LANG=en_US.UTF-8

    # Use optional proxy
    if [ ! -z "$PROXY" ]; then
        cat <<EOF > /etc/apt/apt.conf.d/99otto
Acquire::http::proxy "$PROXY";
Acquire::https::proxy "$PROXY";
EOF
        if ! grep -q "http_proxy" /etc/environment; then
            echo "http_proxy=$PROXY" >> /etc/environment
            echo "https_proxy=$PROXY" >> /etc/environment
        fi
    fi
}

test_setup() {
    # Additional steps to prepare the testing environment
    #
    # This function executes additional steps to prepare the testing
    # environment and syncs the test payload to the target system.
    #
    # Args:
    #   $1: user
    #   $2: test directory
    echo "I: Running test setup"
    if [ $# -ne 2 ]; then
        echo "E: Wrong number of arguments"
        exit 1
    fi
    user=$1
    testdir=$2

    # rsync custom-installation directory to /
    if [ -d "$testdir/target-override" ]; then
        rsync -avH $testdir/target-override/ /
    fi

    # rsync packages directory to otto directory
    mkdir -p /var/local/otto/config/
    if [ -d "$RUNDIR/packages" ]; then
        rsync -avH --no-recursive $RUNDIR/packages/* /var/local/otto/config/
        # if specific release config, overwrite with it
        if [ -d "$RUNDIR/packages/$RELEASE" ]; then
            rsync -avH $RUNDIR/packages/$RELEASE/* /var/local/otto/config/
        fi
    fi

}

user_exists() {
    # Checks if a user exists
    # $1: Username
    if ! getent passwd "$1" 2>/dev/null>/dev/null; then
        return 1
    else
        return 0
    fi
}

prepare_user $TESTUSER
configure_system $TESTUSER
test_setup $TESTUSER $TESTDIR
