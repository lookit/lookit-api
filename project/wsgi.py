"""
WSGI config for project project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/1.9/howto/deployment/wsgi/
"""
import os
from pathlib import Path

from django.core.wsgi import get_wsgi_application
from dotenv import load_dotenv

if os.environ.get("GEVENT") == "1":
    from psycogreen.gevent import patch_psycopg  # noqa

    patch_psycopg()

# Load .env variables here and in manage.py, not only in settings - see
# https://pypi.org/project/python-dotenv/
env_path = Path(__file__).resolve().parents[1] / ".env"
load_dotenv(dotenv_path=env_path, verbose=True)

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "project.settings")

application = get_wsgi_application()
