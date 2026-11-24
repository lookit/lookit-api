from django.contrib import admin
from django.utils import timezone

from accounting import services
from accounting.models import GrantType, LedgerEntry, Lot


@admin.register(Lot)
class LotAdmin(admin.ModelAdmin):
    list_display = (
        "uuid",
        "lab",
        "unit",
        "study",
        "grant_type",
        "amount_granted",
        "amount_remaining",
        "granted_at",
        "expires_at",
        "expired_at",
    )
    list_filter = ("unit", "grant_type", "study", "lab")
    search_fields = ("uuid", "lab__name", "study__name", "notes")
    raw_id_fields = ("lab", "study")
    date_hierarchy = "granted_at"
    list_select_related = ("lab", "study")

    # Fields staff can set when creating a lot. The balance is never entered by hand:
    # it comes from the GRANT entry that services.grant() writes.
    add_fields = (
        "lab",
        "unit",
        "study",
        "grant_type",
        "amount_granted",
        "granted_at",
        "expires_at",
        "consumption_priority",
        "notes",
    )
    # Once the lot exists only these may change; everything else is fixed by the ledger.
    editable_fields = ("expires_at", "consumption_priority", "notes")

    def get_fields(self, request, obj=None):
        if obj is None:
            return self.add_fields
        return (
            "uuid",
            *self.add_fields,
            "amount_remaining",
            "expired_at",
            "created_by",
            "created_at",
            "modified_at",
        )

    def get_readonly_fields(self, request, obj=None):
        if obj is None:
            return ()
        return [
            f for f in self.get_fields(request, obj) if f not in self.editable_fields
        ]

    def get_changeform_initial_data(self, request):
        return {
            "granted_at": timezone.now(),
            **super().get_changeform_initial_data(request),
        }

    def formfield_for_choice_field(self, db_field, request, **kwargs):
        if db_field.name == "grant_type":
            # Deficit lots are created by allocation, never granted by hand.
            kwargs["choices"] = [
                c for c in db_field.get_choices() if c[0] != GrantType.DEFICIT
            ]
        return super().formfield_for_choice_field(db_field, request, **kwargs)

    def save_model(self, request, obj, form, change):
        if change:
            super().save_model(request, obj, form, change)
            return
        created = services.grant(
            obj.lab,
            obj.amount_granted,
            obj.unit,
            obj.grant_type,
            study=obj.study,
            granted_at=obj.granted_at,
            expires_at=obj.expires_at,
            actor=request.user,
            notes=obj.notes,
        )
        if obj.consumption_priority != created.consumption_priority:
            created.consumption_priority = obj.consumption_priority
            created.save(update_fields=["consumption_priority", "modified_at"])
        # Hand the saved lot back to the admin so it redirects to the right object.
        obj.__dict__.update(created.__dict__)

    def has_delete_permission(self, request, obj=None):
        # Every lot has ledger rows (PROTECT), and lots are the balance record.
        return False


@admin.register(LedgerEntry)
class LedgerEntryAdmin(admin.ModelAdmin):
    list_display = (
        "created_at",
        "effective_at",
        "lab",
        "unit",
        "entry_type",
        "amount",
        "lot_balance_after",
        "lot",
        "study",
        "response_uuid",
        "group_id",
    )
    list_filter = ("unit", "entry_type", "lot__grant_type", "lab")
    search_fields = (
        "uuid",
        "group_id",
        "lot__uuid",
        "lab__name",
        "study__name",
        "response__uuid",
        "memo",
    )
    date_hierarchy = "effective_at"
    list_select_related = ("lab", "lot", "study", "response")

    @admin.display(description="Response", ordering="response__uuid")
    def response_uuid(self, obj):
        # Response.__str__ reaches through child and user; the UUID is what staff search by.
        return obj.response.uuid if obj.response_id else None

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
