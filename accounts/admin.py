from django.contrib import admin
from guardian.admin import GuardedModelAdmin

from accounts.models import DemographicData, Organization, Child, User


class ChildAdmin(GuardedModelAdmin):
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
admin.site.register(Child, ChildAdmin)
