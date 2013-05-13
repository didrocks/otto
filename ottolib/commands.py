"""
Commands class - part of the project otto
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
import argparse
import logging
from ottolib import utils, container, const

class Commands(object):
    def __init__(self):
        """ Constructor """
        self.args = None
        self.run = None
        self.container = None
        self.__parse_args()

    def __parse_args(self):
        """ Parse command line arguments """
        parser = argparse.ArgumentParser(
            description="Manages containers used to run automated UI tests "
            "with LXC")
        parser.add_argument('-d', '--debug', action='store_true',
                            default=False, help='enable debug mode')
        subparser = parser.add_subparsers()

        pcreate = subparser.add_parser("create", help="Create a new container")
        pcreate.add_argument("name", help="name of the container")
        pcreate.add_argument("-C", "--config", help="Path to configuration file")
        pcreate.set_defaults(func=self.cmd_create)

        pdestroy = subparser.add_parser("destroy", help="Destroy a container")
        pdestroy.add_argument("name", help="name of the container")
        pdestroy.set_defaults(func=self.cmd_destroy)

        pstart = subparser.add_parser("start", help="Start a container")
        pstart.add_argument("name", help="name of the container")
        pstart.set_defaults(func=self.cmd_start)

        pstop = subparser.add_parser("stop", help="Stop a container")
        pstop.add_argument("name", help="name of the container")
        pstop.set_defaults(func=self.cmd_stop)

        self.args = parser.parse_args()
        utils.set_logging(self.args.debug)
        self.run = self.args.func
        self.container = container.Container(self.args.name)
        logging.debug(self.args)

    def cmd_create(self):
        """ Creates a new container """
        self.container.create()
        return 0

    def cmd_destroy(self):
        """ Destroys a container """
        self.container.destroy()
        return 0

    def cmd_start(self):
        """ Starts a container """
        logging.info("Starting container '%s'", self.args.name)
        logging.info("Container '%s' started", self.args.name)
        return 0

    def cmd_stop(self):
        """ Stops a container """
        logging.info("Stopping container '%s'", self.args.name)
        logging.info("Container '%s' stopped", self.args.name)
        return 0
