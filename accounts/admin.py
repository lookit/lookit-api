from bitfield import BitField
from bitfield.admin import BitFieldListFilter
from bitfield.forms import BitFieldCheckboxSelectMultiple
from django.contrib import admin
from guardian.admin import GuardedModelAdmin

from accounts.models import Child, DemographicData, Message, User


class ChildAdmin(GuardedModelAdmin):
    list_display = ("id", "uuid", "given_name", "birthday", "user")
    # list_filter = (
    # ("existing_conditions", BitFieldListFilter),
    # ("multiple_birth", BitFieldListFilter),
    # leave out until https://github.com/disqus/django-bitfield/issues/64 is fixed
    # )
    date_hierarchy = "birthday"
    search_fields = ["uuid", "given_name"]
    formfield_overrides = {BitField: {"widget": BitFieldCheckboxSelectMultiple}}
    raw_id_fields = ("user",)


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
    # make the interface for adding/removing groups and perms easier to use and
    # harder to screw up
    filter_horizontal = ("groups", "user_permissions")


class DemographicDataAdmin(GuardedModelAdmin):
    list_display = ("uuid", "created_at", "user", "lookit_referrer")
    raw_id_fields = ("user",)


class MessageAdmin(GuardedModelAdmin):
    list_display = ("date_created", "sender", "subject")
    list_filter = ("related_study",)
    raw_id_fields = ("sender", "related_study")
    filter_horizontal = ("recipients",)
    search_fields = ["subject", "body"]


admin.site.register(User, UserAdmin)
admin.site.register(DemographicData, DemographicDataAdmin)
admin.site.register(Child, ChildAdmin)
admin.site.register(Message, MessageAdmin)
