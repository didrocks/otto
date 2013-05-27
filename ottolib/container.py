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
import tarfile
import time

from . import const, errors, utils
from .configgenerator import ConfigGenerator
from .utils import ignored


class ContainerError(errors.OttoError):
    pass


class Container(object):
    """ Class that manages LXC """

    def __init__(self, name, create=False):
        self.name = name
        self.container = lxc.Container(name)
        self.wait = self.container.wait
        self.guestpath = os.path.join(const.LXCBASE, name)
        self.rundir = os.path.join(self.guestpath, const.RUNDIR)

        self.arch = utils.host_arch()

        # Create root tree
        if create:
            if os.path.exists(self.guestpath):
                raise ContainerError("Container already exists. Exiting!")
        else:
            if not os.path.isdir(self.guestpath):
                raise ContainerError("Container {} does not exist.".format(name))

        self._refreshconfig()

    @property
    def running(self):
        return self.container.running

    def create(self):
        """Creates a new container

        This method creates a new container from scratch. We don't want to use
        the create method from LXC API because the bootstrapping phase is not
        required and replaced by using an Ubuntu image directly.
        It creates the minimum files required by LXC to be a valid container:
        rootfs/, config and fstab, copies a pre-mount script that is used
        during when the container starts to prepare the container to run from
        a disk image and share the devices from the host. The directory guest
        will be rsynced to the guest FS by the pre-mount script to install
        additional packages into the container.

        TODO:
            - Verify that the source files exist before the copy
            - Override LXC configuration file or append new directives
            - Override default fstab or append new entries
        """
        logger.info("Creating container '%s'", self.name)

        # Base rootfs
        os.makedirs(os.path.join(self.guestpath, "rootfs"))
        # Scripts
        os.makedirs(os.path.join(self.guestpath, "scripts"))
        # tools and default config from otto
        self._copy_otto_files()

        logger.debug("Done")

    def destroy(self):
        """Destroys a container

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
                raise ContainerError("Path doesn't exist: {}".format(self.guestpath))
        logger.debug("Done")

    def start(self):
        """Starts a container.

        This method refresh with starts a container and wait for START_TIMEOUT before
        aborting.
        """
        if self.running:
            raise ContainerError("Container '{}' already running.".format(self.name))

        # ensure we have a rundir
        with ignored(OSError):
            os.makedirs(self.rundir)
        # regenerate a new runid, even if restarting an old run
        self.config.runid = int(time.time())

        self.config.archivedir = os.path.join(self.guestpath, const.ARCHIVEDIR)

        # tools and default config from otto
        self._copy_otto_files()

        logger.info("Starting container '{}'".format(self.name))
        if not self.container.start():
            raise ContainerError("Can't start lxc container")

        # Wait for the container to start
        self.container.wait('RUNNING', const.START_TIMEOUT)
        logger.info("Container '{}' started".format(self.name))
        if not self.running:
            raise ContainerError("The container didn't start successfully")

    def stop(self):
        """Stops a container

        This method stops a container and wait for STOP_TIMEOUT before
        aborting.
        """
        if not self.running:
            raise ContainerError("Container '{}' already stopped.".format(self.name))

        logger.info("Stopping container '{}'".format(self.name))
        if not self.container.stop():
            raise ContainerError("The lxc command returned an error")

        # Wait for the container to stop
        self.container.wait('STOPPED', const.STOP_TIMEOUT)
        logger.info("Container '{}' stopped".format(self.name))
        if self.running:
            raise ContainerError("The container didn't stop successfully")

    def _refreshconfig(self):
        """Force recreate new config objects attached to the content of
           generated config
        """
        self.config = ConfigGenerator(os.path.join(self.rundir, const.CONFIG_FILE))

    def _copy_otto_files(self):
        """Copy otto files from trunk to container

        This enables to refresh with the latest files from the tree"""

        # Copy files used by the container
        # Substitute name of the container in the configuration file.
        lxcdefaults = os.path.join(utils.get_base_dir(), "lxc.defaults")
        with open(os.path.join(lxcdefaults, "config"), 'r') as fin:
            with open(os.path.join(self.guestpath, "config"), 'w') as fout:
                for line in fin:
                    lineout = line
                    if "${NAME}" in line:
                        lineout = line.replace("${NAME}", self.name)
                    elif "${ARCH}" in line:
                        lineout = line.replace("${ARCH}", self.arch)
                    fout.write(lineout)

        dri_exists = os.path.exists("/dev/dri")
        vga_device = utils.find_vga_device()
        with open(os.path.join(lxcdefaults, "fstab"), 'r') as fin:
            with open(os.path.join(self.guestpath, "fstab"), 'w') as fout:
                for line in fin:
                    if line.startswith("/dev/dri") and not dri_exists:
                        lineout = "# /dev/dri not found, entry disabled ("\
                                "do you use nvidia or fglrx graphics "\
                                "drivers?)\n"
                        lineout += "#" + line
                    else:
                        lineout = line
                    fout.write(lineout)

        src = os.path.join(lxcdefaults, "scripts")
        dst = os.path.join(self.guestpath, "scripts")
        with ignored(OSError):
            shutil.rmtree(dst)
        shutil.copytree(src, dst)
        utils.set_executable(os.path.join(dst, "pre-start.sh"))
        utils.set_executable(os.path.join(dst, "pre-mount.sh"))
        utils.set_executable(os.path.join(dst, "post-stop.sh"))

        src = os.path.join(lxcdefaults, "guest")
        dst = os.path.join(self.guestpath, "guest")
        with ignored(OSError):
            shutil.rmtree(dst)
        shutil.copytree(src, dst)

        # Some graphics need a proprietary driver
        # driver -> packages to install
        drivers = {
            "fglrx": "fglrx",
            "nvidia": "nvidia-current"
        }
        if vga_device is not None and "Driver" in vga_device:
            if vga_device["Driver"] in drivers:
                logging.info("Installing additional drivers for graphics "
                             "card {}".format(vga_device["Device"]))
                # l-h-g must be installed to compile additional modules
                pkgs = "linux-headers-generic {}\n".format(
                    drivers[vga_device["Driver"]])
                pkgsdir = os.path.join(self.guestpath, "guest", "var/local/otto/")
                if not os.path.exists(pkgsdir):
                    os.makedirs(pkgsdir)
                with open(os.path.join(pkgsdir, "00drivers.pkgs"), 'w') as fpkgs:
                    logging.debug("Custom drivers written to {}".format(
                        os.path.join(pkgsdir, "00drivers.pkgs")))
                    fpkgs.write(pkgs)

    def install_custom_installation(self, path):
        """Install a new custom installation, removing previous one if present.

        Return False if any error"""

        logger.info("Customizing container from '{}'".format(path))
        if not os.path.isdir(path):
            return ContainerError("You provided a wrong custom installation path.")

        self.remove_custom_installation()
        for candidate in os.listdir(path):
            src = os.path.join(path, candidate)
            dst = os.path.join(self.rundir, candidate)
            if os.path.isdir(src):
                shutil.copytree(src, dst)
            else:
                shutil.copy(src, dst)

    def remove_custom_installation(self):
        """Delete custom installation content from latest run"""

        logger.info("Removing old customization")
        for candidate in os.listdir(self.rundir):
            if candidate not in ("config", "delta"):
                candidate = os.path.join(self.rundir, candidate)
                try:
                    shutil.rmtree(candidate)
                except NotADirectoryError:
                    os.remove(candidate)

    def setup_local_config(self, file_path):
        """Setup a custom local config"""
        shutil.copy(file_path, os.path.join(self.rundir, const.LOCAL_CONFIG_FILE))

    def remove_local_config(self):
        """Delete previously installed local config"""
        with ignored(OSError):
            os.remove(os.path.join(self.rundir, const.LOCAL_CONFIG_FILE))

    def remove_delta(self):
        """Delete delta content from latest run"""

        logger.info("Removing old delta")
        with ignored(OSError):
            shutil.rmtree(os.path.join(self.rundir, "delta"))

    def restore(self, archive):
        """Restore an old container run"""
        logger.info("Restoring an old archive run from {}".format(archive))
        if os.path.isabs(archive):
            restorefile = archive
        else:
            restorefile = os.path.join(self.guestpath, const.ARCHIVEDIR, archive)
        with ignored(OSError):
            shutil.rmtree(os.path.join(self.rundir))
        with tarfile.open(restorefile, "r:gz") as f:
            f.extractall(self.rundir)
        self._refreshconfig()
