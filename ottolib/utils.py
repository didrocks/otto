"""
Utilities - part of the project otto
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
import logging
import os
import stat

def set_logging(debugmode=False):
    """Initialize logging"""
    logging.basicConfig(
        level=logging.DEBUG if debugmode else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s")
    logging.debug('Debug mode enabled')

def set_executable(path):
    """ Set executable bit on a file """
    st = os.stat(path)
    os.chmod(path, st.st_mode | stat.S_IEXEC)
