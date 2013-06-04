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
import subprocess
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
        if os.getuid() != 0:
            raise ContainerError("You must be root to manage containers")
        self.container = lxc.Container(name)
        self.wait = self.container.wait
        self.containerpath = os.path.join(const.LXCBASE, name)
        self.rundir = os.path.join(self.containerpath, const.RUNDIR)

        self.arch = utils.host_arch()

        # Create root tree
        if create:
            if os.path.exists(self.containerpath):
                raise ContainerError("Container already exists. Exiting!")
        else:
            if not os.path.isdir(self.containerpath):
                raise ContainerError("Container {} does not exist.".format(name))

        self._refreshconfig()

    @property
    def running(self):
        return self.container.running

    def create(self, imagepath, upgrade=False, local_config=None):
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

        It also hardlink the image path passed as parameters so that the container
        "contains" what's needed and do an eventual container start dist-upgrade
        to create a base delta that we'll keep in the container lifetime
        (alongside the eventual archive)

        TODO:
            - Override LXC configuration file or append new directives
            - Override default fstab or append new entries
        """
        logger.info("Creating container '%s'", self.name)

        if not os.path.exists(imagepath):
            raise ContainerError("'{}' doesn't exist. Please specify a valid image path.".format(imagepath))

        # create base path a hardlink the iso
        os.makedirs(self.containerpath)
        container_imagepath = os.path.join(self.containerpath, os.path.basename(imagepath))
        try:
            os.link(imagepath, container_imagepath)
        except OSError:
            # might be on a different partition, fall back to symlink then
            os.symlink(imagepath, container_imagepath)

        self._mountiso(container_imagepath)

        if local_config:
            self.setup_local_config(local_config)

        # Base rootfs
        os.makedirs(os.path.join(self.containerpath, "rootfs"))
        # Tools
        os.makedirs(os.path.join(self.containerpath, "tools"))
        # tools and default config from otto
        self._copy_otto_files()

        self.container.load_config()

        if upgrade:
            self.upgrade()

        logger.debug("Creation done")

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
            if os.path.isdir(self.containerpath) \
                    and self.containerpath.startswith(const.LXCBASE) \
                    and not os.path.exists(
                        os.path.join(self.containerpath, "config")):
                shutil.rmtree(self.containerpath)
            else:
                raise ContainerError("Path doesn't exist: {}".format(self.containerpath))
        logger.debug("Done")

    def upgrade(self):
        """Run and store a dist-upgrade in the container."""
        self.config.basedeltadir = os.path.join(const.BASESDIR, time.strftime("base_%Y.%m.%d-%Hh%Mm%S"))
        logger.debug("Upgrading the container to create a base in {}".format(self.config.basedeltadir))
        basedelta = os.path.join(self.containerpath, self.config.basedeltadir)
        os.makedirs(basedelta)
        self.config.command = "upgrade"
        self.start()
        self.container.wait('STOPPED', const.UPGRADE_TIMEOUT)
        if self.running:
            raise ContainerError("The container didn't stop successfully")
        self.config.command = ""
        if os.path.isfile(os.path.join(basedelta, '.upgrade')):
            raise ContainerError("The upgrade didn't finish successfully")

    def start(self, with_delta=False):
        """Starts a container.

        This method refresh with starts a container and wait for START_TIMEOUT before
        aborting.
        """
        if self.running:
            raise ContainerError("Container '{}' already running.".format(self.name))

        self._mountiso(os.path.join(self.containerpath, self.config.image))
        # check that the container is coherent with our deltas
        (isoid, release, arch) = utils.extract_cd_info(self.config.isomount)
        if self.config.command != "upgrade" and self.config.iso is not None:
            logger.debug("Checking that the container is compatible with the iso.")
            if not (self.config.isoid == isoid and
                    self.config.release == release and
                    self.config.arch == arch):
                raise ContainerError("Can't reuse a previous run delta: the previous run was used with "
                             "{deltaisoid}, {deltarelease}, {deltaarch} and {imagepath} is for "
                             "{isoid}, {release}, {arch}. config use a compatible container."
                             "".format(deltaisoid=self.config.isoid,
                                       deltarelease=self.config.release,
                                       deltaarch=self.config.arch,
                                       isoid=isoid, release=release, arch=arch,
                                       imagepath=self.config.image))
            if self.config.basedeltadir:
                logger.debug("Check that the delta has a compatible base delta in the container")
                if not os.path.isdir(os.path.join(self.containerpath, self.config.basedeltadir)):
                    raise ContainerError("No base delta found as {}. This means that we can't reuse "
                                         "this previous run with it. Please use a compatible container "
                                         "or restore this base delta.".format(self.config.basedeltadir))
        self.config.isoid = isoid
        self.config.release = release
        self.config.arch = arch

        # regenerate a new runid, even if restarting an old run
        self.config.runid = int(time.time())

        self.config.archivedir = const.ARCHIVEDIR

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
            with open(os.path.join(self.containerpath, "config"), 'w') as fout:
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
            with open(os.path.join(self.containerpath, "fstab"), 'w') as fout:
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
        dst = os.path.join(self.containerpath, "tools", "scripts")
        with ignored(OSError):
            shutil.rmtree(dst)
        shutil.copytree(src, dst)
        utils.set_executable(os.path.join(dst, "pre-start.sh"))
        utils.set_executable(os.path.join(dst, "pre-mount.sh"))
        utils.set_executable(os.path.join(dst, "post-stop.sh"))

        src = os.path.join(lxcdefaults, "guest")
        dst = os.path.join(self.containerpath, "tools", "guest")
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
                # TODO: this shouldn't be in the guest directory
                pkgsdir = os.path.join(self.containerpath, "tools", "guest", "var", "local", "otto", "config")
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
        try:
            shutil.copy(file_path, os.path.join(self.rundir, const.LOCAL_CONFIG_FILE))
        except OSError as e:
            raise ContainerError("Local config file provided errored out: {}".format(e))

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
            restorefile = os.path.join(self.containerpath, const.ARCHIVEDIR, archive)
        with ignored(OSError):
            shutil.rmtree(os.path.join(self.rundir))
        with tarfile.open(restorefile, "r:gz") as f:
            f.extractall(self.rundir)
        self._refreshconfig()

    def _mountiso(self, container_imagepath):
        """Mount iso from container_imagepath"""
        (isomount, squashfs) = utils.get_iso_and_squashfs(container_imagepath)
        if isomount is None or squashfs is None:
            shutil.rmtree(self.containerpath)
            raise ContainerError("Couldn't mount or extract squashfs from {}".format(container_imagepath))

        self.config.isomount = isomount
        self.config.squashfs = squashfs
        self.config.image = os.path.basename(container_imagepath)

        logger.debug("selected iso is {}, and squashfs is: {}".format(self.config.isomount,
                                                                      self.config.squashfs))

    def unmountiso(self):
        """Enable unmouting the iso (used in case of failure)"""
        # the iso wasn't mounted yet
        if not self.config.isomount:
            return
        logger.info("Try unmounting the iso: {}".format(self.config.isomount))
        try:
            subprocess.check_call(["umount", self.config.isomount])
        except subprocess.CalledProcessError as cpe:
            logger.info("couldn't unmount the iso ({}): {}".format(cpe.returncode, cpe.output))
