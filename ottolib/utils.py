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

from contextlib import contextmanager
import logging
logger = logging.getLogger(__name__)
import os
import shutil
import stat
import subprocess
import sys


def set_logging(debugmode=False):
    """ Initialize logging """
    basic_formatting = "%(asctime)s %(levelname)s %(message)s"
    if debugmode:
        basic_formatting = "<%(module)s:%(lineno)d - %(threadName)s> " + \
            basic_formatting
    logging.basicConfig(format=basic_formatting)
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG if debugmode else logging.INFO)
    logger.debug('Debug mode enabled')


def set_executable(path):
    """ Set executable bit on a file """
    stt = os.stat(path)
    os.chmod(path, stt.st_mode | stat.S_IEXEC)


def service_start(service):
    """ Start an upstart service

    @service: Name of the service

    @return: True if command is successful
    """
    return service_start_stop(service, "start")


def service_stop(service):
    """ Start an upstart service

    @service: Name of the service

    @return: True if command is successful
    """
    return service_start_stop(service, "stop")


def service_is_running(service):
    """ Status of an upstart service

    @return: True if service if running False if not and -1 on error
    """
    if service_exists(service) != 0:
        return -1

    cmd = ["status", service]
    try:
        msg = subprocess.check_output(cmd)
    except subprocess.CalledProcessError:
        # Happens if the service doesn't exist on the system
        logger.error("'status {}' failed with error:\n{}".format(service, msg))
        return -1

    if b"start/running" in msg:
        logger.debug("Service '%s' is running", service)
        return True
    elif b"stop/waiting" in msg:
        logger.debug("Service '%s' is stopped", service)
        return False
    else:
        return -1


def service_exists(service):
    """ Checks that a service exists on the system

    @service: Name of the service

    @return: 0 if it exists, 1 if not and -1 on error
    """
    cmd = ["status", service]
    try:
        subprocess.check_output(cmd)
        return 0
    except subprocess.CalledProcessError as cpe:
        if b"status: Unknown job:" in cpe.output:
            return 1
        else:
            # Unknown Error
            logger.error(
                "'{}' failed with error:\n{}".format(cmd, cpe.output))
            return -1


def service_start_stop(service, start):
    """ Start/Stop an upstart service

    @service: Name of the service
    @start: start or stop

    @return: 0   on success,
             1   on failure,
             2   if service doesn't exist,
             3   not enough privileges
             99  on any other error
    """
    if os.getuid() != 0:
        logger.error("You must be root to manage upstart services. Aborting!")
        return 3

    exists = service_exists(service)
    if exists < 0:
        return -1
    if exists == 1:
        return 2

    # Return immediatly if the service is already in the required state
    status = service_is_running(service)
    if status < 0:  # 'status service' returned an error
        return 99

    if status == (start == "start"):
        logger.info("Service '%s' already in state '%s'", service, start)
    else:
        cmd = [start.lower(), service.lower()]
        logger.debug("Executing: %s", cmd)
        try:
            subprocess.check_output(cmd)
        except subprocess.CalledProcessError as cpe:
            logger.error(
                "'{}' failed with status %d:\n{}".format(
                    cmd, cpe.returncode, cpe.output))
            return 1

    return 0


def get_image_type(path):
    """ Returns the types of an image passed in argument

    @path: Path to the image

    @return: one of the type in the 'types' dictionary, 'unknown' if the type
    is not in the dictionary or 'error'
    """
    # signature -> type
    imgtypes = {
        "# ISO 9660 CD-ROM filesystem": "iso9660",
        "x86 boot sector"; "iso9660",
        "Squashfs filesystem": "squashfs"
    }
    if not os.path.isfile(path):
        logger.warning("File '%s' does not exist!", path)
        return "error"

    cmd = ["file", "-L", "-b", path]

    try:
        msg = subprocess.check_output(cmd, universal_newlines=True)
    except subprocess.CalledProcessError as cpe:
        logger.error("'{}' failed with status %d:\n{}".format(
            cmd, cpe.returncode, cpe.output))
        return "error"

    for sig, imgtype in imgtypes.items():
        if msg.lower().startswith(sig.lower()):
            logger.debug("Found type '%s' for file '%s'", imgtype, path)
            return imgtype
    return "unknown"


def get_iso_and_squashfs(image):
    """Get path to squashfs

    Image should be an iso9660 file system, it gets loop-mounted and
    a tuple countaining (iso_path, squash_fs) path is returned

    @image: path to a squashfs or iso9660 image
    @return: (iso_path, squash_path)
    """

    if get_image_type(image) != "iso9660":
        logger.error("image '%s' is not an iso9660", image)
        return None

    # mount the ISO, unless it is already
    iso_mount = "/run/otto/iso/" + image.replace("/", "_")
    squashfs_path = os.path.join(iso_mount, "casper", "filesystem.squashfs")
    if subprocess.call(["mountpoint", "-q", iso_mount]) != 0:
        logger.debug("%s not mounted yet, creating and mounting", iso_mount)
        try:
            os.makedirs(iso_mount)
        except OSError:
            pass
        try:
            subprocess.check_call(["mount", "-n", "-o", "loop", image, iso_mount])
        except subprocess.CalledProcessError as cpe:
            logger.error(
                "mounting iso failed with status %d:\n{}".format(
                    cpe.returncode, cpe.output))

    if not os.path.isfile(squashfs_path):
        logger.error("'%s' does not contain /casper/filesystem.squashfs", image)
        return (None, None)
    logger.debug("found squashfs on ISO image: %s", squashfs_path)
    return (iso_mount, squashfs_path)

def extract_cd_info(image_path):
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

def exit_missing_imports(modulename, package):
    """ Exit if a required import is missing """
    try:
        __import__(modulename)
    except ImportError as exc:
        print("{}: you need to install {}".format(exc, package))
        sys.exit(1)


def exit_missing_command(command, package):
    """Exit if a command is missing"""
    if not shutil.which(command):
        print("{} is missing: you need to install {}".format(command, package))
        sys.exit(1)


def get_bin_dir():
    """ Get otto bin dir path """
    return sys.path[0]


def get_base_dir():
    """ Get base dir for otto """
    potential_basedir = os.path.abspath(os.path.dirname(get_bin_dir()))
    if os.path.isdir(os.path.join(potential_basedir, "ottolib")):
        return potential_basedir
    else:
        return os.path.join("/", "usr", "share", "otto")


def host_arch():
    """ Returns host architecture like dpkg --print-architecture

    @return: arch
    """
    try:
        arch = subprocess.check_output(["dpkg", "--print-architecture"])
        return arch.decode().strip()
    except subprocess.CalledProcessError as cpe:
        logging.error("dpkg call failed with status %d:\n{}".format(
            cpe.returncode, cpe.output))
        return None


def find_vga_device():
    """ Find VGA device on the host. lspci is used to collect information
    about devices on the host. It populates a dictionary with the devices
    specifications.

    @return: A dicto containing device information
    """
    cmd = ['lspci', '-knnvmm']
    try:
        lspci_out = subprocess.check_output(cmd)
    except subprocess.CalledProcessError as cpe:
        logger.warning("lspci call failed with {}".format(cpe))
        return None

    device_info = {}
    graphics_card = None
    for line in lspci_out.decode().split('\n'):
        if line.strip():
            (tag, value) = line.split(':', 1)
            device_info[tag] = value.strip()
        elif device_info:
            if "Class" in device_info:
                if device_info["Class"].endswith("[0300]"):
                    graphics_card = dict(device_info)
                    break
            device_info = {}
    logging.debug("Found graphics card {}".format(graphics_card))
    return graphics_card


# this is stolen from python 3.4 :)
@contextmanager
def ignored(*exceptions):
    try:
        yield
    except exceptions:
        pass
