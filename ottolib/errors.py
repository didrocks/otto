"""
Class for handling custom exceptions
"""

# Copyright (C) 2013 Canonical
#
# Authors: Jean-Baptiste Lallement <jean-baptiste.lallement@canonical.com>
#
# This program is free software; you can redistribute it and/or modify it
# under
# the terms of the GNU General Public License as published by the Free
# Software
# Foundation; version 3.
#
# This program is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or
# FITNESS
# FOR A PARTICULAR PURPOSE.  See the GNU General Public License for more
# details.
#
# You should have received a copy of the GNU General Public License along with
# this program; if not, write to the Free Software Foundation, Inc.,
# 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA


class OttoError(Exception):
    """
    Parent class  to handle custom exceptions. Custom exception will subclass
    it.
    """
    def __init__(self, msg=None, **kwds):
        """
        Constructor
        """
        Exception.__init__(self)
        for key, value in kwds.items():
            setattr(self, key, value)
        self._msg = msg

    def _format(self):
        s = getattr(self, '_msg', None)
        if s is not None:
            return s

        try:
            fmt = getattr(self, "_fmt", None)
            if fmt:
                d = dict(self.__dict__)
                s = fmt % d
                return s
        except Exception as e:
            pass
        else:
            e = None
        return 'Unprintable exception %s: dict=%r, fmt=%r, error=%r' \
            % (self.__class__.__name__,
               self.__dict__,
               getattr(self, '_fmt', None),
               e)

    def __str__(self):
        s = self._format()
        return s

    def __repr__(self):
        return '%s(%s)' % (self.__class__.__name__, str(self))

    @property
    def errorcode(self):
        """
        returncode can be overriden in a subclass otherwise 255 is returned
        """
        return self._errorcode if hasattr(self, "_errorcode") else 255
