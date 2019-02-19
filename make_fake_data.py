import os

import django
from django_dynamic_fixture import G

from accounts.models import Organization, User
from studies.models import Response, Study

os.environ["DJANGO_SETTINGS_MODULE"] = "project.settings"

django.setup()  # noqa


for x in range(0, 100):
    G(Response)

org = G(Organization)
User.objects.all().update(organization=org)
Study.objects.all().update(state="active")
