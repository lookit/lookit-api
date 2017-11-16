from django.contrib import admin
from guardian.admin import GuardedModelAdmin

from accounts.models import DemographicData, Organization, Child, User


class ChildAdmin(GuardedModelAdmin):
    list_display = ('id', 'uuid', 'given_name', 'birthday', 'user')
    list_filter = ('id', 'uuid',)


class UserAdmin(GuardedModelAdmin):
    list_display = ('id', 'uuid', 'nickname', 'given_name', 'family_name', 'is_staff', 'is_researcher', 'date_created', 'last_login')
    list_filter = ('id', 'uuid',)

class OrganizationAdmin(GuardedModelAdmin):
    pass


class DemographicDataAdmin(GuardedModelAdmin):
    list_display = ('id', 'uuid', 'created_at', 'user')
    list_filter = ('id', 'uuid',)

admin.site.register(User, UserAdmin)
admin.site.register(Organization, OrganizationAdmin)
admin.site.register(DemographicData, DemographicDataAdmin)
admin.site.register(Child, ChildAdmin)
