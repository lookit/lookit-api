from __future__ import absolute_import, unicode_literals

import warnings

# This will make sure the app is always imported when
# Django starts so that shared_task will use this app.
from .celery import app as celery_app

__all__ = ["celery_app"]

# If dotenv is installed (dev environment), load .env variables here. This is done *before* setting remaining values,
# so that e.g. DEBUG from .env is used to determine other values. Note this will not overwrite any system-level
# environment variables (e.g. in .bashrc)
try:
    from dotenv import find_dotenv, load_dotenv
except ImportError:
    warnings.warn(
        "Module dotenv not available; not importing local settings from .env",
        ImportWarning,
    )
else:
    env_path = find_dotenv()
    if not env_path:
        warnings.warn("Expected .env file not found; not importing local settings")
    else:
        load_dotenv(dotenv_path=env_path, verbose=True)
