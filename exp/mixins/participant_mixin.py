from django.contrib.auth.mixins import (
    PermissionRequiredMixin as DjangoPermissionRequiredMixin,
)
from django.db.models import Prefetch
from guardian.shortcuts import get_objects_for_user

from accounts.models import User, Child
from studies.models import get_consented_responses_qs


class ParticipantMixin(DjangoPermissionRequiredMixin):
    """Mixin with shared items for Participant Detail and Participant List Views"""

    permission_required = "accounts.can_view_experimenter"
    raise_exception = True
    model = User

    def get_queryset(self):
        """
        Restricts queryset to participants that a researcher has permission to view.
        """
        studies = get_objects_for_user(self.request.user, "studies.can_view_study")
        valid_study_ids = studies.values_list("id", flat=True)
        valid_child_ids = (
            get_consented_responses_qs()
            .filter(study__id__in=valid_study_ids)
            .values_list("child", flat=True)
        )

        return (
            User.objects.filter(children__in=valid_child_ids)
            .prefetch_related(
                Prefetch(
                    "children", queryset=Child.objects.filter(id__in=valid_child_ids)
                )
            )
            .distinct()
        )
