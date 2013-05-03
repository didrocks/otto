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

TESTBASE=/var/local/autopilot/
AP_ARTIFACTS=$TESTBASE/results/artifacts
AP_RESULTS=$TESTBASE/results/tests
AP_OPTS="-v -r -rd $AP_ARTIFACTS -f xml"

[ -f /etc/default/tests/config ] && . /etc/default/tests/config

SPOOLDIR=$TESTBASE/spool

setup_tests() {
    # Prepares the environment for the tests
    flag=$HOME/.ap_setup_done

    [ -e "$flag" ] && return 0

    # Disable notifications
    gsettings set com.ubuntu.update-notifier show-apport-crashes false

    # Loads the list of test and queue them in test spool
    mkdir -p $SPOOLDIR $AP_ARTIFACTS $AP_RESULTS
    
    # Test Only - Generate a subset of tests to run
    for testsuite in $(autopilot list unity.tests.launcher | grep -E '^ (\*[0-9]+|\s*)? '| sed -e 's/ \(.*\)\? //'|cut -d'.' -f3|sort -u); do
        touch $SPOOLDIR/$testsuite
    done
    touch $flag
}

run_tests() {
    # Runs all the tests in spooldir
    if [ "$(ls  $SPOOLDIR 2>/dev/null)" ]; then
        testname="$(ls $SPOOLDIR/ 2>/dev/null|head -1)"
        autopilot run $testname $AP_OPTS -o $AP_RESULTS/$testname.xml
        rm -f $SPOOLDIR/$testname
    else
        echo "I: No test to run. Shutting down"
    fi
}

setup_tests
run_tests
