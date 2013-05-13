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
import subprocess


def set_logging(debugmode=False):
    """Initialize logging"""
    logging.basicConfig(
        level=logging.DEBUG if debugmode else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s")
    logging.debug('Debug mode enabled')


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

    cmd = "status %s" % service
    (ret, msg) = subprocess.getstatusoutput(cmd)

    if ret != 0:
        return -1

    if "start/running" in msg:
        logging.debug("Service '%s' is running", service)
        return True
    elif "stop/waiting" in msg:
        logging.debug("Service '%s' is stopped", service)
        return False

    # Happens if the service doesn't exist on the system
    logging.error("'status %s' failed with exit status %d:\n%s", service, ret,
                  msg)
    return -1


def service_exists(service):
    """ Checks that a service exists on the system

    @service: Name of the service

    @return: 0 if it exists, 1 if not and -1 on error
    """
    cmd = "status %s" % service

    (ret, msg) = subprocess.getstatusoutput(cmd)

    if ret == 0:
        return 0

    if ret == 256 and "status: Unknown job:" in msg:
        return 1

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
        logging.error("You must be root to manage upstart services. Aborting!")
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
        logging.info("Service '%s' already in state '%s'", service, start)
    else:
        cmd = "%s %s" % (start.lower(), service.lower())
        logging.debug("Executing: %s", cmd)
        (ret, msg) = subprocess.getstatusoutput(cmd)

        if ret != 0:
            logging.error("'%s' failed with status %d:\n%s", cmd, ret, msg)
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
        "Squashfs filesystem": "squashfs"
    }
    if not os.path.isfile(path):
        logging.warning("File '%s' does not exist!", path)
        return "error"

    (ret, msg) = subprocess.getstatusoutput("file -b %s" % path)
    if ret != 0:
        return "error"
    else:
        for sig, imgtype in imgtypes.iteritems():
            if msg.lower.startswith(sig.lower()):
                return imgtype
        return "unknown"


def copy_squashfs(image, destdir):
    """ Copy a squashfs to destdir

    If the image passed in argument is an ISO, the squashfs is extracted to
    destdir. The version of the image is extracted from the squashfs to
    clearly identify it (release, arch) The buildid is also extracted if the
    file media-info is found on the image.

    @image: path to an image
    @destdir: destination path

    @return: (distro, release, arch, buildid)
    """
    pass
