"""
Class to manage LXC - part of the project otto
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

import logging
logger = logging.getLogger(__name__)
import lxc
import os
import shutil
import sys

from . import const, utils
from .configgenerator import ConfigGenerator


class Container(object):
    """ Class that manages LXC """

    def __init__(self, name):
        self.name = name
        self.container = lxc.Container(name)
        self.wait = self.container.wait
        self.guestpath = os.path.join(const.LXCBASE, name)
        self.lxcdefaults = os.path.join(utils.get_base_dir(), "lxc.defaults")
        self.script_src = os.path.join(self.lxcdefaults, "scripts")
        self.script_dst = os.path.join(self.guestpath, "scripts")
        self.otto_config = ConfigGenerator(self.script_src, self.script_dst)

    @property
    def squashfs_path(self):
        return self.otto_config.squashfs_path

    @squashfs_path.setter
    def squashfs_path(self, value):
        self.otto_config.squashfs_path = value

    @property
    def running(self):
        return self.container.running

    def create(self):
        """ Creates a new container

        This method creates a new container from scratch. We don't want to use
        the create method from LXC API because the bootstrapping phase is not
        required and replaced by using an Ubuntu image directly.
        It creates the minimum files required by LXC to be a valid container:
        rootfs/, config and fstab, copies a pre-mount script that is used
        during when the container starts to prepare the container to run from
        a disk image and share the devices from the host. The directory guest
        will be rsynced to the guest FS by the pre-mount script to install
        additional packages into the container.

        @return: 0 on success, 1 otherwise

        TODO:
            - Verify that the source files exist before the copy
            - Override LXC configuration file or append new directives
            - Override default fstab or append new entries
            - Specify a release (Could this information be extracted from
              squashfs?)
            - Normalize return codes as currently the same RC can mean
              different things
        """
        logger.info("Creating container '%s'", self.name)

        # Create root tree
        if os.path.exists(self.guestpath):
            logger.error("Container already exists. Exiting!")
            sys.exit(1)

        # Base rootfs
        os.makedirs(os.path.join(self.guestpath, "rootfs"))
        # Scripts
        os.makedirs(os.path.join(self.guestpath, "scripts"))

        # Copy files used by the container
        # Substitute name of the container in the configuration file.
        with open(os.path.join(self.lxcdefaults, "config"), 'r') as fin:
            with open(os.path.join(self.guestpath, "config"), 'w') as fout:
                for line in fin:
                    fout.write(line.replace("${NAME}", self.name))

        shutil.copy(os.path.join(self.lxcdefaults, "fstab"), self.guestpath)

        shutil.copy(os.path.join(self.script_src, "pre-mount.sh"),
                    self.script_dst)
        utils.set_executable(os.path.join(self.script_dst, "pre-mount.sh"))
        shutil.copy(os.path.join(self.script_src, const.DEFAULT_CONFIG_FILE),
                    self.script_dst)

        src = os.path.join(self.lxcdefaults, "guest")
        dst = os.path.join(self.guestpath, "guest")
        shutil.copytree(src, dst)

        logger.debug("Done")
        return 0

    def destroy(self):
        """ Destroys a container

        The container is destroyed with the LXC API and we fallback to rmtree()
        if it fails to cover the case of a partially created LXC container i.e
        a directory tree without a configuration file
        """
        logger.info("Removing container '%s'", self.name)
        if not self.container.destroy():
            logger.warning("lxc-destroy failed, trying to remove directory")
            # We check that LXCBASE/NAME/config exists because if it does then
            # lxc destroy should have succeeded and the failure is elsewhere,
            # for example the container is still running
            if os.path.isdir(self.guestpath) \
                    and self.guestpath.startswith(const.LXCBASE) \
                    and not os.path.exists(
                        os.path.join(self.guestpath, "config")):
                shutil.rmtree(self.guestpath)
            else:
                logger.info("Path doesn't exist '%s'. Ignoring.",
                            self.guestpath)
                return 1
        logger.debug("Done")
        return 0

    def start(self):
        """ Starts a container.

        This method starts a container and wait for START_TIMEOUT before
        aborting.

        @return: 0 on success 1 on failure
        """
        if self.running:
            logger.warning("Container '%s' already running. Skipping!")
            return 0

        logger.info("Starting container '%s'", self.name)
        if not self.container.start():
            logging.error("Can't start lxc container")
            return 1

        # Wait for the container to start
        self.container.wait('RUNNING', const.START_TIMEOUT)
        logger.info("Container '%s' started", self.name)
        return 0 if self.running else 1

    def stop(self):
        """ Stops a container

        This method stops a container and wait for STOP_TIMEOUT before
        aborting.

        @return: 0 on success 1 on failure
        TODO:
            - Do not stop if already stopped
        """
        if not self.running:
            logger.warning("Container '%s' already stopped. Skipping!")
            return 0

        logger.info("Stopping container '%s'", self.name)
        if not self.container.stop():
            return 1

        # Wait for the container to stop
        self.container.wait('STOPPED', const.STOP_TIMEOUT)
        logger.info("Container '%s' stopped", self.name)
        return 0 if not self.running else 1
