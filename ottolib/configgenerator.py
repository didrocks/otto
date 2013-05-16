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
from .utils import ignored


class ConfigGenerator(object):
    """Class that manages LXC dynamic configuration.

    We generate a rundir/config file that are going to be used by LXC"""

    def __init__(self, rundir):

        self._config_file = os.path.join(rundir, "config")

        # if exists, load old parameters
        if os.path.isfile(self._config_file):
            self.__load_parameters_from_file(self._config_file)

    def __setattr__(self, name, value):
        """Ask to save if the attribute make sense to be saved."""
        # check that the attribute really changed if it existed
        with ignored(AttributeError):
            if getattr(self, name) == value:
                return
        object.__setattr__(self, name, value)
        if not name.startswith("_") and not self._loading_from_file:
            self.__write()

    def __write(self):
        """Collect all overriden values and generate the override file"""
        config = self.get_config()
        logger.debug("Save otto configuration file with {}".format(config))
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
        logger.debug("Loaded previous config file. Values are {}.".format(self.get_config()))
        self._loading_from_file = False

    def get_config(self):
        """Return a dictionnary with the relevant config content"""
        all_attr = self.__dict__
        return {key: all_attr[key] for key in all_attr if not key.startswith("_")}
