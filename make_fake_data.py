import os

import django

os.environ['DJANGO_SETTINGS_MODULE'] = 'project.settings'

django.setup()  # noqa

from accounts.models import Organization, User
from django_dynamic_fixture import G
from studies.models import Response, Study

for x in range(0, 100):
    G(Response)

org = G(Organization)
User.objects.all().update(organization=org)
Study.objects.all().update(state='active')
