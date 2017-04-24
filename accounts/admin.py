from django.contrib import admin

from accounts.models import DemographicData, Organization

from .models import User

admin.site.register(User)
admin.site.register(Organization)
admin.site.register(DemographicData)
