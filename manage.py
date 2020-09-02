#!/usr/bin/env python
import os
import sys

if os.environ.get("GEVENT") == "1":
    from gevent import monkey

    monkey.patch_all()

    from psycogreen.gevent import patch_psycopg

    patch_psycopg()

if __name__ == "__main__":
    from dotenv import load_dotenv
    from pathlib import Path

    # Load .env variables here and in wsgi.py, not only in settings - see
    # https://pypi.org/project/python-dotenv/
    env_path = Path(__file__).resolve().parents[1] / ".env"
    load_dotenv(dotenv_path=env_path, verbose=True)

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "project.settings")

    from django.core.management import execute_from_command_line

    execute_from_command_line(sys.argv)
