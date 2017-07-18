"""
WSGI config for project project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/1.9/howto/deployment/wsgi/
"""
import os

if os.environ.get('GEVENT') == '1':
    from gevent import monkey
    monkey.patch_all()

    from psycogreen.gevent import patch_psycopg  # noqa
    patch_psycopg()

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "project.settings")

application = get_wsgi_application()
