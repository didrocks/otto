"""
config_generate - part of the project otto
"""

# Copyright (C) 2013 Canonical
#
# Authors: Didier Roche <didier.roche@canonical.com>
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
import os
from . import const


class ConfigGenerator(object):
    """ Class that manages LXC dynamic configuration.

    It's generate an otto.rc file that will be sourced by the premount.sh script """

    def __init__(self, script_src, dest_override_path):

        self.overriden_config = {}
        self.default_config_file = os.path.join(script_src,
                                                const.DEFAULT_CONFIG_FILE)
        self.override_config_file = os.path.join(dest_override_path,
                                                 "{}.override".format(const.DEFAULT_CONFIG_FILE))
        self.__load_parameters_from_file(self.default_config_file)
        if os.path.isfile(self.override_config_file):
            self.__load_parameters_from_file(self.override_config_file)

    @property
    def squashfs_path(self):
        return self._squashfs_path

    @squashfs_path.setter
    def squashfs_path(self, value):
        logger.debug("override SQUASHFS_PATH to {}".format(self.squashfs_path))
        self._squashfs_path = value
        self.overriden_config["SQUASHFS_PATH"] = self.squashfs_path
        self.__write_overwrite_file()

    def __write_overwrite_file(self):
        """ Collect all overriden values and generate the override file """
        logger.debug("Save otto override configuration file")
        with open(self.override_config_file, 'w') as f:
            for overriden_value in self.overriden_config:
                f.write("{}={}".format(overriden_value, self.overriden_config[overriden_value]))

    def __load_parameters_from_file(self, filepath):
        """ Load and set parameters from file """
        logger.debug("Reading configuration file for otto premount "
                     " script {}".format(filepath))
        with open(filepath, 'r') as f:
            for line in f:
                if line.startswith("CACHE_DIR="):
                    self.cache_dir = line.split("=")[1][:-1]
                elif line.startswith("SQUASHFS_PATH="):
                    self._squashfs_path = line.split("=")[1][:-1]
                    self._squashfs_path = self.squashfs_path.replace("$CACHE_DIR",
                                                                    self.cache_dir)
        logger.debug("Values are CACHE_DIR={cache_dir}, "
                     "SQUASHFS_PATH={squashfs_path}".format(
                        cache_dir=self.cache_dir,
                        squashfs_path=self.squashfs_path))
