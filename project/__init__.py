from __future__ import absolute_import, unicode_literals

import warnings
from pathlib import Path

# This will make sure the app is always imported when
# Django starts so that shared_task will use this app.
from .celery import app as celery_app

__all__ = ["celery_app"]


try:
    from dotenv import load_dotenv
except ImportError:
    warnings.warn(
        "Module dotenv not available; not importing local settings from .env",
        ImportWarning,
    )
else:
    # Load .env variables here, *before* setting remaining values, so that e.g. DEBUG from .env is used to
    # determine other values. Note this will not overwrite any system-level environment variables (e.g. in .bashrc)
    env_path = Path(__file__).resolve().parents[1] / ".env"
    load_dotenv(dotenv_path=env_path, verbose=True)
