from django import forms
from django.conf import settings
from django.contrib import admin, messages
from django.contrib.admin.views.main import SEARCH_VAR
from django.core.exceptions import ValidationError
from django.db.models import Count
from django.urls import reverse
from django.utils import timezone
from django.utils.html import format_html
from django_countries import countries

from web import geoip
from web.middleware import get_client_ip
from web.models import BlockRule, ParticipationBlockRecord, Visitor, describe


class BlockRuleAdminForm(forms.ModelForm):
    # Set by BlockRuleAdmin.get_form.
    request = None

    class Meta:
        model = BlockRule
        fields = "__all__"

    def clean(self):
        """Don't let admins block their own IP address from the entire site,
        which would lock them out of the admin.
        """
        cleaned_data = super().clean()
        if (
            self.request is None
            or not cleaned_data.get("block_entire_site")
            or not cleaned_data.get("is_active")
        ):
            return cleaned_data
        rule = BlockRule(
            kind=cleaned_data.get("kind"), value=cleaned_data.get("value") or ""
        )
        try:
            rule.value = rule.canonical_value()
        except ValidationError:
            # Shown on the value field.
            return cleaned_data
        problem = lockout_problem(self.request, rule)
        if problem:
            raise ValidationError(
                {
                    "block_entire_site": f"{problem} Uncheck this to block only "
                    "participation."
                }
            )
        return cleaned_data


def lockout_problem(request, rule):
    """Why blocking the entire site with `rule` could lock the admin making
    `request` out of the admin, or None if it couldn't.
    """
    try:
        match_value = BlockRule.match_value(rule.kind, rule.value)
        visitor = Visitor(get_client_ip(request))
    except ValueError:
        # A malformed rule, which doesn't block anyone, or no IP address of our
        # own to check.
        return None
    edition = BlockRule.GEOIP_EDITIONS.get(rule.kind)
    problem = edition and geoip.problem(edition)
    if problem:
        return (
            "Can't check whether this rule includes your own IP address "
            f"({visitor.address}), which would lock you out of the admin, because "
            f"{problem}."
        )
    if visitor.matches(rule.kind, match_value):
        return (
            f"{rule} includes your own IP address ({visitor.address}), so this "
            "would lock you out of the admin."
        )
    return None


@admin.action(description="Activate selected rules")
def activate_selected(modeladmin, request, queryset):
    # Like the edit form, don't let admins lock themselves out of the admin.
    refused = []
    for rule in queryset.filter(is_active=False, block_entire_site=True):
        problem = lockout_problem(request, rule)
        if problem:
            modeladmin.message_user(
                request,
                f"Didn't activate {rule}, which blocks the entire site: {problem} "
                "Edit it to block only participation instead.",
                messages.ERROR,
            )
            refused.append(rule.pk)
    # update() skips save() and post_save, so set updated_at and clear the
    # block rule cache ourselves.
    updated = queryset.exclude(pk__in=refused).update(
        is_active=True, updated_at=timezone.now()
    )
    BlockRule.clear_cache()
    if updated:
        modeladmin.message_user(
            request, f"Activated {updated} block rule(s).", messages.SUCCESS
        )


@admin.action(description="Deactivate selected rules (keep them)")
def deactivate_selected(modeladmin, request, queryset):
    # update() skips save() and post_save, so set updated_at and clear the
    # block rule cache ourselves.
    updated = queryset.update(is_active=False, updated_at=timezone.now())
    BlockRule.clear_cache()
    modeladmin.message_user(
        request, f"Deactivated {updated} block rule(s).", messages.SUCCESS
    )


@admin.register(BlockRule)
class BlockRuleAdmin(admin.ModelAdmin):
    form = BlockRuleAdminForm
    list_display = (
        "rule",
        "kind",
        "currently_blocking",
        "block_entire_site",
        "is_active",
        "expires_at",
        "short_reason",
        "participants_stopped",
        "created_by",
        "created_at",
    )
    list_filter = ("kind", "is_active", "block_entire_site")
    search_fields = ("value", "reason")
    readonly_fields = ("created_by", "created_at", "updated_at")
    fields = (
        "kind",
        "value",
        "reason",
        "block_entire_site",
        "is_active",
        "expires_at",
        "created_by",
        "created_at",
        "updated_at",
    )
    date_hierarchy = "created_at"
    actions = (activate_selected, deactivate_selected)

    @admin.display(description="Rule", ordering="value")
    def rule(self, obj):
        return str(obj)

    @admin.display(boolean=True, description="Currently blocking")
    def currently_blocking(self, obj):
        return obj.in_effect

    @admin.display(description="Reason")
    def short_reason(self, obj):
        return obj.reason if len(obj.reason) <= 60 else f"{obj.reason[:57]}..."

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        form.request = request
        return form

    def changelist_view(self, request, extra_context=None):
        # Actions POST here and then redirect, so this avoids showing the
        # messages twice.
        if request.method == "GET":
            self.add_status_messages(request)
        return super().changelist_view(request, extra_context)

    def add_status_messages(self, request):
        """Warn about anything stopping the rules from blocking, and describe
        the IP address being searched for, if any.
        """
        if not settings.BLOCK_RULES_ENABLED:
            self.message_user(
                request,
                "Block rules are switched off (BLOCK_RULES_ENABLED is false), so "
                "none of these rules are blocking anyone.",
                messages.WARNING,
            )
        elif settings.BLOCK_RULES_REPORT_ONLY:
            self.message_user(
                request,
                "Block rules are in report-only mode (BLOCK_RULES_REPORT_ONLY is "
                "true): participants they match are logged and recorded, but can "
                "still participate. Rules that block the entire site still block it.",
                messages.WARNING,
            )
        try:
            visitor = Visitor(request.GET.get(SEARCH_VAR, "").strip())
        except ValueError:
            visitor = None
        for kind, edition in BlockRule.GEOIP_EDITIONS.items():
            problem = geoip.problem(edition)
            if problem and (
                visitor or BlockRule.objects.in_effect().filter(kind=kind).exists()
            ):
                self.message_user(
                    request,
                    f"{kind.label} rules aren't blocking anyone, because {problem}.",
                    messages.WARNING,
                )
        if visitor:
            self.message_user(
                request,
                f"{describe(visitor)}. Showing the rules that apply to it.",
                messages.INFO,
            )

    @admin.display(description="Participants stopped", ordering="participants")
    def participants_stopped(self, obj):
        """How many logged-in participants the rule has stopped, linking to
        them.
        """
        if not obj.participants:
            return 0
        url = reverse("admin:web_participationblockrecord_changelist")
        return format_html('<a href="{}?rule={}">{}</a>', url, obj.pk, obj.participants)

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .select_related("created_by")
            .annotate(participants=Count("participation_block_records"))
        )

    def get_search_results(self, request, queryset, search_term):
        """Searching for an IP address finds the rules that apply to it, and
        searching for a country by name finds its rule.
        """
        unsearched = queryset
        queryset, may_have_duplicates = super().get_search_results(
            request, queryset, search_term
        )
        term = search_term.strip()
        code = countries.by_name(term)
        if code:
            queryset |= unsearched.filter(kind=BlockRule.Kind.COUNTRY, value=code)
        try:
            visitor = Visitor(term)
        except ValueError:
            return queryset, may_have_duplicates
        matching_ids = []
        for pk, kind, value in unsearched.values_list("pk", "kind", "value"):
            try:
                if visitor.matches(kind, BlockRule.match_value(kind, value)):
                    matching_ids.append(pk)
            except ValueError:
                # A malformed value, which the lookups skip too.
                continue
        return (
            queryset | unsearched.filter(pk__in=matching_ids),
            may_have_duplicates,
        )

    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(ParticipationBlockRecord)
class ParticipationBlockRecordAdmin(admin.ModelAdmin):
    """Who each rule has stopped participating. Made by the site, so admins
    can view and delete these but not add or change them.
    """

    list_display = (
        "user",
        "rule",
        "times_blocked",
        "first_blocked_at",
        "last_blocked_at",
        "network",
        "country",
        "network_owner",
    )
    list_filter = ("rule__kind", "country")
    search_fields = (
        "user__username",
        "user__uuid",
        "rule__value",
        "network",
        "asn_organization",
    )
    list_select_related = ("user", "rule")
    date_hierarchy = "last_blocked_at"

    @admin.display(description="Network owner", ordering="asn")
    def network_owner(self, obj):
        if obj.asn is None:
            return ""
        if obj.asn_organization:
            return f"AS{obj.asn} ({obj.asn_organization})"
        return f"AS{obj.asn}"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
