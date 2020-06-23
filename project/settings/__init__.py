# -*- coding: utf-8 -*-
"""Consolidates settings from defaults.py and local.py.
"""
import itertools
import os
import warnings

from .defaults import *  # noqa

try:
    from .local import *  # noqa
except ImportError as error:
    warnings.warn(
        "No project/settings/local.py settings file found. Did you remember to "
        "copy local-dist.py to local.py?",
        ImportWarning,
    )
