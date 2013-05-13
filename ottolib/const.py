"""
Various Constants - part of the project otto
"""

# Copyright (C) 2013 Canonical
#
# Authors: Jean-Baptiste Lallement <jean-baptiste.lallement@canonical.com>
#
# This program is free software; you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation; version 3.
#
# This program is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
# FOR A PARTICULAR PURPOSE.  See the GNU General Public License for more
# details.
#
# You should have received a copy of the GNU General Public License along with
# this program; if not, write to the Free Software Foundation, Inc.,
# 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA
#
import sys
import os

LXCBASE = "/var/lib/lxc"
BINDIR = os.path.abspath(sys.path[0])

if os.path.isdir(os.path.join(BINDIR, "../ottolib/")):
    BASEDIR = os.path.normpath(os.path.join(BINDIR, ".."))
    # Run from source tree
    LXCDEFAULTS = os.path.join(BASEDIR, "lxc.defaults")
else:
    LXCDEFAULTS = "/usr/share/otto/lxc.defaults"
