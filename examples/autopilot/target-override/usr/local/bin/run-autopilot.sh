#!/bin/sh -eu

#
# This script runs autopilot
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
exec 2>&1

TESTBASE=/var/local/autopilot/
AP_ARTIFACTS=$TESTBASE/results/artifacts
AP_RESULTS=$TESTBASE/results/tests
AP_OPTS="-v -r -rd $AP_ARTIFACTS -f xml"
AP_TESTSUITES=$TESTBASE/testsuites

# Define general configuration files 
[ -f $TESTBASE/config ] && . $TESTBASE/config

SPOOLDIR=$TESTBASE/spool

setup_tests() {
    # Prepares the environment for the tests
    flag=$HOME/.ap_setup_done

    [ -e "$flag" ] && return 0

    # Disable notifications and screensaver
    gsettings set com.ubuntu.update-notifier show-apport-crashes false
    gsettings set org.gnome.desktop.screensaver idle-activation-enabled false

    # Loads the list of test and queue them in test spool
    sudo mkdir -p $SPOOLDIR $AP_ARTIFACTS $AP_RESULTS
    sudo chown $USER:$USER $SPOOLDIR $AP_ARTIFACTS $AP_RESULTS
    
    # Test Only - Generate a subset of tests to run
    #for testsuite in $(autopilot list unity.tests.launcher | grep -E '^ (\*[0-9]+|\s*)? '| sed -e 's/ \(.*\)\? //'|cut -d'.' -f3|sort -u); do
    #    touch $SPOOLDIR/$testsuite
    #done
    if [ -e "$AP_TESTSUITES" ]; then
        (cd $SPOOLDIR; touch $(cat $AP_TESTSUITES))
    fi
    touch $flag
}

run_tests() {
    # Runs all the tests in spooldir
    #
    # $1: Spool directory
    spooldir=$1
    if [ ! -d $spooldir ]; then
        echo "E: '$spooldir is not a directory. Exiting!"
        exit 1
    fi

    for testfile in $(ls $spooldir/ 2>/dev/null); do
        testname=$(basename $testfile)
        autopilot run $testname $AP_OPTS -o $AP_RESULTS/$testname.xml
        rm -f $testfile
    done

    if [ ! "$(ls -A $spooldir/)" ]; then
        echo "I: No test left to run"
        shutdown -h now 
    fi
}

setup_tests
run_tests $SPOOLDIR
