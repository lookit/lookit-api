from django.contrib import admin

from accounts.models import DemographicData, Organization, Profile, User
from guardian.admin import GuardedModelAdmin


class ProfileAdmin(GuardedModelAdmin):
    pass


class UserAdmin(GuardedModelAdmin):
    pass


class OrganizationAdmin(GuardedModelAdmin):
    pass


class DemographicDataAdmin(GuardedModelAdmin):
    pass


admin.site.register(User, UserAdmin)
admin.site.register(Organization, OrganizationAdmin)
admin.site.register(DemographicData, DemographicDataAdmin)
admin.site.register(Profile, ProfileAdmin)
