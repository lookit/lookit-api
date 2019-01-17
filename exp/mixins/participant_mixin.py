from django.contrib.auth.mixins import \
    PermissionRequiredMixin as DjangoPermissionRequiredMixin
from guardian.shortcuts import get_objects_for_user

from accounts.models import User


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
        study_ids = studies.values_list("id", flat=True)
        return User.objects.filter(
            children__response__study__id__in=study_ids
        ).distinct()
