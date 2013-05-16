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

from glob import glob
import hashlib
import logging
logger = logging.getLogger(__name__)
import os
import shutil
import stat
import subprocess
import sys
from tempfile import TemporaryDirectory
from time import gmtime, strftime


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
        if "status: Unknown job:" in cpe.output:
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
        "Squashfs filesystem": "squashfs"
    }
    if not os.path.isfile(path):
        logger.warning("File '%s' does not exist!", path)
        return "error"

    cmd = ["file", "-b", path]

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


def copy_image(image, destpath):
    """ Copy a squashfs to destpath

    If the image passed in argument is an ISO, the squashfs is extracted to
    destdir. The version of the image is extracted from the squashfs to
    clearly identify it (release, arch) The buildid is also extracted if the
    file media-info is found on the image.

    @image: path to an image
    @destpath: destination path, including filename
               (it will be a symlink within the same directory)

    @return: Path to squashfs file in cache
    """
    logger.info("Updating cached squashfs from '%s'", image)
    image_type = get_image_type(image)

    squashfs_src = None
    squashfs_dst = None
    md5sum = None

    destdir = os.path.abspath(os.path.dirname(destpath))

    with TemporaryDirectory(prefix="otto.") as tmpdir:
        if image_type == "iso9660":
            # Extract md5sum.txt from ISO and loads checksums
            md5sum_path = extract_file_from_iso("md5sum.txt", image, tmpdir)
            md5sums = {}
            with open(md5sum_path) as fmd5:
                for line in fmd5:
                    (digest, filename) = line.strip().split(maxsplit=1)
                    md5sums[filename] = digest

            # The squashfs is extracted from the ISO only if it doesn't
            # already exists in the cache directory. We ensure that it is
            # unique by naming the cached file with the md5sum of the
            # squashfs. Since the ISO is read-only, it is always
            # the same for a given build.
            md5sum = md5sums["./casper/filesystem.squashfs"]
            cached_files = glob(os.path.join(destdir, "*-%s.squashfs" %
                                             md5sum))
            if len(cached_files) == 0:
                squashfs_src = extract_file_from_iso(
                    "casper/filesystem.squashfs", image, tmpdir)
                squashfs_md5 = compute_md5sum(squashfs_src)
                if squashfs_md5 != md5sum:
                    logger.error("Checksum of '%s' validation failed. "
                                 "Expected '%s', got '%s'. Aborting!")
                    return None
            else:
                squashfs_src = cached_files[0]

        # Process a squashfs file.
        # squashfs_src has been set after the extraction from the ISO if an
        # ISO was passed as argument or it is the image name if the type of
        # the image is 'squashfs'
        if image_type == "squashfs" or squashfs_src is not None:
            # Copy squashfs to cache directory
            if squashfs_src is None:
                squashfs_src = image
            if md5sum is None:
                md5sum = compute_md5sum(squashfs_src)

            cached_files = glob(os.path.join(
                destdir, "*-%s.squashfs" % md5sum))
            if len(cached_files) > 0:  # Should be 1 really
                logger.debug("File '%s' already in cache", cached_files[0])
                squashfs_dst = cached_files[0]
            else:
                # Extract metadata from the squashfs
                sqfs_root = extract_file_from_squashfs(
                    "squashfs-root", squashfs_src,
                    os.path.join(tmpdir, "squashfs-root"))
                # squashfs-root is the root directory and unsquashfs is called
                # with -d which will extract it to dest without squashfs-root
                # leading extract_file_from_squashfs to a name like
                # $tmpdir/squashfs-root/squashfs-root but only
                # $tmpdir/squashfs-root/ exists, so the last part must be
                # stripped as it doesn't exists
                sqfs_root = sqfs_root.rsplit('/', 1)[0]
                sqfs_root_ts = strftime("%Y%m%d_%H",
                                        gmtime(os.path.getmtime(sqfs_root)))

                # Copy it to destination directory
                squashfs_dst = "filesystem-%s-%s.squashfs" % (
                    sqfs_root_ts, md5sum)
                if not os.path.exists(destdir):
                    os.makedirs(destdir)
                shutil.copy2(squashfs_src, os.path.join(destdir, squashfs_dst))

            # Recreate symlink to this file
            destlink = os.path.join(destdir, "filesystem.squashfs")
            logger.debug("Updating symlink '%s'", destlink)
            if os.path.islink(destlink):
                os.unlink(destlink)
            os.symlink(squashfs_dst, destlink)

    return squashfs_dst


def extract_file_from_iso(filename, iso, dest):
    """ Extract a file from an ISO
    """
    if not shutil.which("bsdtar"):
        logger.error("bsdtar not found in path. It is needed to extract iso "
                     "files")
    cmd = ["bsdtar", "xf", iso, "-C", dest, filename]
    try:
        logger.debug("Extracting %s from %s to %s", filename, iso, dest)
        subprocess.check_call(cmd)
        out = os.path.join(dest, filename)
        return out
    except subprocess.CalledProcessError:
        return None


def extract_file_from_squashfs(filename, sqfs, dest):
    """ Extract a file from an ISO
    """
    if not shutil.which("unsquashfs"):
        logger.error("unsquashfs not found in path. It is needed to extract "
                     "squashfs files")
    cmd = ["unsquashfs",  "-f", "-n", "-d", dest, sqfs, filename]
    try:
        logger.debug("Extracting %s from %s to %s", filename, sqfs, dest)
        subprocess.check_call(cmd)
        out = os.path.join(dest, filename)
        return out
    except subprocess.CalledProcessError:
        return None


def compute_md5sum(filename):
    """ Validate an MD5 checksum """
    block_size = 2**20
    logger.debug("Calculating hash for file '%s'", filename)
    md5sum = hashlib.md5()
    with open(filename, "rb") as fhd:
        while True:
            data = fhd.read(block_size)
            if not data:
                break
            md5sum.update(data)

    logger.debug("Local File Checksum: '%s'", md5sum.hexdigest())
    return md5sum.hexdigest()


def exit_missing_imports(modulename, package):
    """ Exit if a required import is missing """
    try:
        __import__(modulename)
    except ImportError as exc:
        print("{}: you need to install {}".format(exc, package))
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
