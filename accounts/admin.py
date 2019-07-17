from django.contrib import admin
from guardian.admin import GuardedModelAdmin
from bitfield import BitField
from bitfield.forms import BitFieldCheckboxSelectMultiple
from bitfield.admin import BitFieldListFilter


from accounts.models import Child, DemographicData, Organization, User


class ChildAdmin(GuardedModelAdmin):
    list_display = ("id", "uuid", "given_name", "birthday", "user")
    list_filter = (
        "id",
        "uuid",
        # ("existing_conditions", BitFieldListFilter),
        # ("multiple_birth", BitFieldListFilter),
        # leave out until https://github.com/disqus/django-bitfield/issues/64 is fixed
    )
    date_hierarchy = "birthday"
    search_fields = ["uuid", "given_name"]
    formfield_overrides = {BitField: {"widget": BitFieldCheckboxSelectMultiple}}


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
