from django.contrib import admin

from accounts.models import DemographicData

from .models import User

admin.site.register(User)
admin.site.register(DemographicData)
