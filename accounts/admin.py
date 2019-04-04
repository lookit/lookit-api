from django.contrib import admin
from guardian.admin import GuardedModelAdmin

from accounts.models import Child, DemographicData, Organization, User


class ChildAdmin(GuardedModelAdmin):
    list_display = ("id", "uuid", "given_name", "birthday", "user")
    list_filter = ("id", "uuid")
    date_hierarchy = "birthday"
    search_fields = ["uuid", "given_name"]


class UserAdmin(GuardedModelAdmin):
    list_display = (
        "id",
        "uuid",
        "nickname",
        "given_name",
        "family_name",
        "is_researcher",
        "date_created",
        "last_login",
    )
    list_filter = ("is_researcher",)
    exclude = ("is_superuser", "is_staff")
    search_fields = ["uuid", "nickname", "given_name", "family_name"]


class OrganizationAdmin(GuardedModelAdmin):
    pass


class DemographicDataAdmin(GuardedModelAdmin):
    list_display = ("uuid", "created_at", "user")
    list_filter = ("user", "country", "lookit_referrer", "number_of_children")


admin.site.register(User, UserAdmin)
admin.site.register(Organization, OrganizationAdmin)
admin.site.register(DemographicData, DemographicDataAdmin)
admin.site.register(Child, ChildAdmin)
