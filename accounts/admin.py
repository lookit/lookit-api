from django.contrib import admin

from accounts.models import DemographicData, Organization
from guardian.admin import GuardedModelAdmin

from .models import User


class UserAdmin(GuardedModelAdmin):
    pass

class OrganizationAdmin(GuardedModelAdmin):
    pass

class DemographicDataAdmin(GuardedModelAdmin):
    pass


admin.site.register(User, UserAdmin)
admin.site.register(Organization, OrganizationAdmin)
admin.site.register(DemographicData, DemographicDataAdmin)
