"""
configgenerator - part of the project otto
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

from .utils import ignored


class ConfigGenerator(object):
    """Class that manages dynamic configurations.

    Map to an object with properties to a config file"""

    def __init__(self, config_file):

        self._config_file = config_file

        # if exists, load old parameters
        self._loading_from_file = False
        if os.path.isfile(self._config_file):
            self.__load_parameters_from_file(self._config_file)

    def __getattr__(self, name):
        """Return None if the attr doesn't exist"""
        return None

    def __setattr__(self, name, value):
        """Ask to save if the attribute make sense to be saved."""
        # check that the attribute really changed if it existed
        if value is None or getattr(self, name) == value:
            return
        object.__setattr__(self, name, value)
        if not name.startswith("_") and not self._loading_from_file:
            self.__write()

    def __write(self):
        """Collect all overriden values and generate the override file"""
        config = self.get_config()
        logger.debug("Save otto configuration file with {}".format(config))
        # ensure we have a rundir
        with ignored(OSError):
            os.makedirs(os.path.dirname(self._config_file))
        with open(self._config_file, 'w') as f:
            for key in config:
                f.write("{}={}\n".format(key.upper(), config[key]))

    def __load_parameters_from_file(self, filepath):
        """ Load and set parameters from file """
        logger.debug("Reading configuration file for otto scripts "
                     "{}".format(filepath))
        self._loading_from_file = True
        with open(filepath, 'r') as f:
            for line in f:
                results = line.split("=")
                if len(results) != 2:
                    continue
                (key, value) = (results[0].strip().lower(), results[1].strip())
                setattr(self, key, value)
        logger.debug("Loaded previous config for {}. Values are {}.".format(filepath,
                                                                            self.get_config()))
        self._loading_from_file = False

    def get_config(self):
        """Return a dictionnary with the relevant config content"""
        all_attr = self.__dict__
        return {key: all_attr[key] for key in all_attr if not key.startswith("_")}
