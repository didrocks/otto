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

import argparse
import logging
logger = logging.getLogger(__name__)
import os
import subprocess
import sys
import shutil
from textwrap import dedent

from . import const, container, utils


class Commands(object):
    """ Available commands for otto

    This class parses the command line, does some basic checks and sets the
    method for the command passed on the command line
    """

    def __init__(self):
        self.args = None
        self.run = None
        self.container = None
        self.__parse_args()

    def __parse_args(self):
        """ Parse command line arguments """
        parser = argparse.ArgumentParser(
            formatter_class=argparse.RawDescriptionHelpFormatter,
            description=dedent('''\
                Manages containers to run automated UI tests with LXC.

                This script must be run with root privileges without any user logged into a
                graphical session as the display manager will be shutdown.
                Physical devices (video, sound and input) are shared between the host and the
                guest, and any action on one side will have effects on the other side, so it is
                recommended to not touch the device under test while the test is running.
                               '''))
        parser.add_argument('-d', '--debug', action='store_true',
                            default=False, help='enable debug mode')
        subparser = parser.add_subparsers(title='commands',
                                          dest='cmd_name')

        pcreate = subparser.add_parser("create", help="Create a new container")
        pcreate.add_argument("name", help="name of the container")
        pcreate.set_defaults(func=self.cmd_create)

        pdestroy = subparser.add_parser("destroy", help="Destroy a container")
        pdestroy.add_argument("name", help="name of the container")
        pdestroy.set_defaults(func=self.cmd_destroy)

        pstart = subparser.add_parser("start", help="Start a container")
        pstart.add_argument("name", help="name of the container")
        pstart.add_argument("-i", "--image",
                            default=None,
                            help="iso or squashfs to use as rootfs. If an "
                            "ISO is used, the squashfs contained in this "
                            "image will be extracted and used as rootfs")
        pstart.add_argument("-C", "--custom-installation",
                            default=None,
                            help="custom-installation directory to use for "
                            "this run")
        pstart.add_argument('-D', '--force-disconnect', action='store_true',
                            default=False,
                            help="Forcibly shutdown lightdm even if a session "
                            "is running and a user might be connected.")
        pstart.set_defaults(func=self.cmd_start)

        pstop = subparser.add_parser("stop", help="Stop a container")
        pstop.add_argument("name", help="name of the container")
        pstop.set_defaults(func=self.cmd_stop)

        phelp = subparser.add_parser("help",
                                     help="Get help on one of those commands")
        phelp.add_argument("command",
                           help="name of the command to get help on")
        phelp.set_defaults(help=self.cmd_stop)

        cmd_parsers = {"create": pcreate, "destroy": pdestroy,
                       "start": pstart, "stop": pstop, "help": phelp}

        self.args = parser.parse_args()
        utils.set_logging(self.args.debug)
        if self.args.cmd_name == "help":
            try:
                cmd_parsers[self.args.command].print_help()
            except KeyError:
                parser.print_help()
            sys.exit(0)
        else:
            self.run = self.args.func
            try:
                self.container = container.Container(self.args.name)
            except Exception as exc:
                logger.error("Error when trying to initiate the container: "
                             "{}".format(exc))
                sys.exit(1)

    def cmd_create(self):
        """ Creates a new container """
        return self.container.create()

    def cmd_destroy(self):
        """ Destroys a container """
        return self.container.destroy()

    def cmd_start(self):
        """ Starts a container

        @return: Return code of Container.start() method
        """
        # Don't shoot any logged in user
        if not self.args.force_disconnect:
            try:
                subprocess.check_call(["pidof", "gnome-session"])
                logger.warning("gnome-session is running. This likely means "
                               "that a user is logged in and will be "
                               "forcibly disconnected. Please logout before "
                               "starting the container or use option -D")
                return 1
            except subprocess.CalledProcessError:
                pass

        srv = "lightdm"
        ret = utils.service_stop(srv)
        if ret > 2:  # Not enough privileges or Unknown error: Abort
            logger.error("An error occurred while stopping service '{}'. "
                         "Aborting!".format(srv))
            return ret

        # An image has been passed on the cmdline, dump the squashfs to
        # cache directory
        destlink = os.path.join(self.container.guestpath, "image.iso")
        if self.args.image is not None:
            # Create a symlink in the container directory to reuse it if -i is
            # not passed on next run
            if os.path.islink(destlink):
                os.unlink(destlink)
            os.symlink(self.args.image, destlink)
        else:
            if not os.path.exists(destlink):
                logger.error("No image provided on the command line and '{}' "
                             "doesn't exist. Please specify an image with -i. "
                             "Exiting!".format(destlink))
                return 1

        imagepath = os.path.realpath(destlink)
        self.container.squashfs_path = utils.get_squashfs(imagepath)
        if self.container.squashfs_path is None:
            return 1

        logger.debug("selected squashfs is: {}".format(
            self.container.squashfs_path))
        if not os.path.isfile(self.container.squashfs_path):
            logger.error("{} doesn't exist. Please provide an iso or a "
                         "squashfs when starting the container.".format(
                             self.container.squashfs_path))
            return 1

        if self.args.custom_installation is not None:
            if os.path.isdir(self.args.custom_installation):
                logger.info("Customizing container from "
                            "'{}'".format(self.args.custom_installation))
                shutil.copytree(self.args.custom_installation,
                                os.path.join(self.container.guestpath,
                                             'custom-installation'))

        if not self.container.start():
            return 1

        # Block until the end of the container
        #
        # NOTE:
        # This doesn't support reboots of the container yet. To support
        # reboots we'd need to check that the container is still stopped a
        # little while after the initial 'STOPPED' state. If it is back to
        # 'RUNNING' it'd mean the container restarted, then it should block on
        # 'STOPPED' again with a new timeout = TEST_TIMEOUT -
        # time_elapsed_since_start_of_the_session
        self.container.wait('STOPPED', const.TEST_TIMEOUT)
        if self.container.running:
            logger.error("Test didn't stop within %d seconds",
                         const.TEST_TIMEOUT)
            self.container.stop()  # Or kill
            return 1
        return 0

    def cmd_stop(self):
        """ Stops a container """
        logger.info("Stopping container '{}'".format(self.args.name))
        logger.info("Container '{}' stopped".format(self.args.name))
        # TODO:
        #   - Wait for stop
        return self.container.stop()
