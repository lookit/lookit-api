from django.db.models import Prefetch, Q

from accounts.models import Child, User
from studies.permissions import StudyPermission
from studies.queries import get_consented_responses_qs, studies_for_which_user_has_perm


class ParticipantMixin:
    """Mixin with shared items for Participant Detail and Participant List Views"""

    model = User

    def valid_responses(self):
        study_ids_real_data = studies_for_which_user_has_perm(
            self.request.user, StudyPermission.READ_STUDY_RESPONSE_DATA
        ).values_list("id", flat=True)
        study_ids_preview_data = studies_for_which_user_has_perm(
            self.request.user, StudyPermission.READ_STUDY_PREVIEW_DATA
        ).values_list("id", flat=True)
        return get_consented_responses_qs().filter(
            Q(study__id__in=study_ids_real_data, is_preview=False)
            | Q(study__id__in=study_ids_preview_data, is_preview=True)
        )

    def get_queryset(self):
        """
        Restricts queryset to participants that a researcher has permission to view.
        """
        valid_child_ids = self.valid_responses().values_list("child", flat=True)
        return (
            User.objects.filter(children__in=valid_child_ids)
            .prefetch_related(
                Prefetch(
                    "children", queryset=Child.objects.filter(id__in=valid_child_ids)
                )
            )
            .distinct()
        )
