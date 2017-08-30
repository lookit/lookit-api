import os

ALLOWED_HOSTS = ('*', )
DEBUG = True
STATIC_URL = '/static/'

# base url for experiments, should be s3 bucket in prod
EXPERIMENT_BASE_URL = os.environ.get('EXPERIMENT_BASE_URL', 'http://localhost:4200')  # default to ember base url
BASE_URL = os.environ.get('BASE_URL', 'http://localhost:8000')  # default to ember base url

EMAIL_HOST_USER = 'D4nkM3m35C4n'
EMAIL_HOST_PASSWORD = 'M31tSt331B34m5'
EMAIL_FROM_ADDRESS = 'lookit.robot@some.domain'
EMAIL_BACKEND = f"django.core.mail.backends.{'console' if DEBUG else 'smtp'}.EmailBackend"
