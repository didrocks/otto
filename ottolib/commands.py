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
from textwrap import dedent

from . import const, container, utils
from .container import ContainerError


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
        pstart.add_argument("image",
                            help="iso to use as rootfs. The squashfs contained in this "
                                 "image will be extracted and used as rootfs")
        pstart.add_argument("-u", "--upgrade", action='store_true',
                            default=False,
                            help="Do and store persistenly an additional dist-upgrade "
                                 "delta that will be stored and use within the container.")

        pdestroy = subparser.add_parser("destroy", help="Destroy a container")
        pdestroy.add_argument("name", help="name of the container")
        pdestroy.set_defaults(func=self.cmd_destroy)

        pstart = subparser.add_parser("start", help="Start a container")
        pstart.add_argument("name", help="name of the container")
        pstart.add_argument("-C", "--custom-installation",
                            default=None,
                            help="custom-installation directory to use for "
                                 "this run")
        pstart.add_argument("--new", action='store_true',
                            default=False,
                            help="remove latest custom-installation directory for a vanilla "
                                 "container run")
        pstart.add_argument("-k", "--keep-delta", action='store_true',
                            default=False,
                            help="Keep delta from latest run to restart in the exact same state")
        pstart.add_argument("-s", "--archive", action='store_true',
                            default=False,
                            help="Archive the run result in a container state file")
        pstart.add_argument("-r", "--restore",
                            default=None,
                            help="Restore a previous the run state from an archive")
        pstart.add_argument("--local-config",
                            default=None,
                            help="Use a local configuration file. This one will be reuse until you specify --no-local-config")
        pstart.add_argument("--no-local-config", action='store_true',
                            default=None,
                            help="Remove previously used local configuration file.")
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
            try:
                self.run = self.args.func
            except:
                self.run = None
                parser.print_help()
            try:
                self.container = container.Container(
                    self.args.name, create = self.args.cmd_name=="create")
            except ContainerError as exc:
                logger.error("Error when trying to use the container: "
                             "{}".format(exc))
                sys.exit(1)

    def cmd_create(self):
        """ Creates a new container """
        try:
            imagepath = os.path.realpath(self.args.image)
            self.container.create(imagepath)
            return 0
        except ContainerError as e:
            logger.error(e)
            return 1

    def cmd_destroy(self):
        """ Destroys a container """
        try:
            self.container.destroy()
            return 0
        except ContainerError as e:
            logger.error(e)
            return 1

    def cmd_start(self):
        """ Starts a container

        @return: Return code of Container.start() method
        """
        # handling incompatible CLI parameters
        # Restoring from a previous state mean keeping the delta
        if self.args.restore:
            self.args.keep_delta = True
        if self.args.restore and (self.args.custom_installation or self.args.new):
            logger.error("Can't restore while asking a new custom-installation or starting afresh "
                         "(new).")
            return 1

        # first, check that the container is not running
        if self.container.running:
            logger.warning("Container '{}' already running.".format(self.container.name))
            return 1

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

        # Hack on the host system for people wanting to run lxc-start directly
        if not os.path.isfile("/etc/apparmor.d/disable/usr.bin.lxc-start"):
            logger.warning("lxc-start is still under apparmor protection. "
                           "If you intend to run lxc-start directly, it will not work. "
                           "You should run:\n"
                           "$ sudo ln -s /etc/apparmor.d/usr.bin.lxc-start /etc/apparmor.d/disable/\n"
                           "$ sudo /etc/init.d/apparmor reload")

        # state saving handling
        if self.args.restore:
            try:
                self.container.restore(self.args.restore)
            except FileNotFoundError as e:
                logger.error("Selected archive doesn't exist. Can't restore: {}.".format(e))
                return 1

        container_config = self.container.config

        # image handling
        if self.args.image is not None:
            imagepath = os.path.realpath(self.args.image)
        else:
            try:
                imagepath = container_config.image
            except AttributeError:
                logger.error("No image provided on the command line and you didn't "
                             "have any previous run into that container. "
                             "Please specify an image with -i.")
                return 1
            if not os.path.exists(imagepath):
                logger.error("No image provided on the command line and '{}' "
                             "doesn't exist. Please specify an image with -i. ".format(imagepath))
                return 1

        # mount and get iso and squashfs path
        (isomount, squashfs) = utils.get_iso_and_squashfs(imagepath)
        if isomount is None or squashfs is None:
            return 1
        container_config.isomount = isomount
        container_config.squashfs = squashfs
        container_config.image = imagepath
        logger.debug("selected iso is {}, and squashfs is: {}".format(container_config.isomount,
                                                                      container_config.squashfs))

        # custom installation handling
        if self.args.new:
            self.container.remove_custom_installation()
        custom_installation = self.args.custom_installation
        if custom_installation is not None:
            try:
                self.container.install_custom_installation(custom_installation)
            except ContainerError as e:
                logger.error(e)
                return 1

        # local configuration handling
        if self.args.local_config:
            try:
                self.container.setup_local_config(self.args.local_config)
            except OSError as e:
                logger.error("Local config file provided errored out: {}".format(e))
                sys.exit(1)
        elif self.args.no_local_config:
            self.container.remove_local_config()

        # get iso infos and manage delta
        (isoid, release, arch) = self._extract_cd_info(isomount)
        if self.args.keep_delta:
            logger.debug("Checking that the iso is compatible with the delta.")
            if not (container_config.isoid == isoid and
                    container_config.release == release and
                    container_config.arch == arch):
                logger.error("Can't reuse a previous run delta: the previous run was used with "
                             "{deltaisoid}, {deltarelease}, {deltaarch} and {imagepath} is for "
                             "{isoid}, {release}, {arch}. Please provide the same iso in parameter."
                             "".format(deltaisoid=container_config.isoid,
                                       deltarelease=container_config.release,
                                       deltaarch=container_config.arch,
                                       isoid=isoid, release=release, arch=arch,
                                       imagepath=imagepath))
                return(1)
        else:
            self.container.remove_delta()
        container_config.isoid = isoid
        container_config.release = release
        container_config.arch = arch

        # that enable us to overwrite the restored "archive" state from restore()
        # if we don't want to resave the restored run
        container_config.archive = self.args.archive

        try:
            self.container.start()
        except ContainerError as e:
            logger.error(e)
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
        #self.container.wait('STOPPED', const.TEST_TIMEOUT)
        #if self.container.running:
        #    logger.error("Test didn't stop within %d seconds",
        #                 const.TEST_TIMEOUT)
        #    self.container.stop()  # Or kill
        #    return 1
        return 0

    def cmd_stop(self):
        """ Stops a container """
        try:
            self.container.stop()
            return 0
        except ContainerError as e:
            logger.error(e)
            return 1
        return 0

    def _extract_cd_info(self, image_path):
        """Extract CD infos and return them (isoid, release, arch)"""
        with open(os.path.join(image_path, ".disk", "info")) as f:
            isoid = f.read().replace("\"", "").replace(" ", "_").replace('-',
                                           "_").replace("(", "").replace(")",
                                           "").replace("___", "_").lower()
        for candidate_release in os.listdir(os.path.join(image_path, "dists")):
            if candidate_release not in ('stable', 'unstable'):
                release = candidate_release
        with open(os.path.join(image_path, "README.diskdefines")) as f:
            for line in f:
                if line.startswith("#define ARCH  "):
                    arch = line.split()[-1]
        return (isoid, release, arch)
