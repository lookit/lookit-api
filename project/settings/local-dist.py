import os

ALLOWED_HOSTS = ('*', )
DEBUG = True

# base url for experiments, should be s3 bucket in prod
EXPERIMENT_BASE_URL = os.environ.get('EXPERIMENT_BASE_URL', 'http://localhost:4200')  # default to ember base url
