from unittest.mock import patch

from django.test.testcases import TestCase

from exp.views.analytics import StudyParticipantAnalyticsView


class StudyParticipantAnalyticsViewTestCase(TestCase):
    @patch.object(StudyParticipantAnalyticsView, "request", create=True)
    @patch("accounts.models.Child.objects")
    def test_get_context_data_deleted_children_perms_true(
        self, mock_child_objects, mock_request,
    ):
        mock_request.user.has_perm.return_value = True

        view = StudyParticipantAnalyticsView()
        view.get_context_data()

        print(mock_child_objects)

        mock_child_objects.filter.assert_called_once_with(
            user__is_researcher=False, deleted=False
        )
        mock_request.user.has_perm.assert_called_with(
            "accounts.can_view_all_children_in_analytics"
        )

    @patch.object(StudyParticipantAnalyticsView, "request", create=True)
    @patch("exp.views.analytics.get_annotated_responses_qs")
    @patch("accounts.models.Child.objects")
    def test_get_context_data_deleted_children_perms_false(
        self, mock_child_objects, mock_get_annotated_responses_qs, mock_request
    ):
        mock_request.user.has_perm.return_value = False

        view = StudyParticipantAnalyticsView()
        view.get_context_data()

        mock_child_objects.filter.assert_called_once_with(
            deleted=False,
            user__is_researcher=False,
            id__in=mock_get_annotated_responses_qs()
            .filter()
            .select_related()
            .values()
            .values_list()
            .distinct(),
        )
        mock_request.user.has_perm.assert_called_with(
            "accounts.can_view_all_children_in_analytics"
        )


# TODO: StudyParticipantAnalyticsView
# - check can get iff self.request.user.has_perm("accounts.can_view_analytics")
#             and self.request.user.is_researcher
# - check context has appropriate number of responses in response_timeseries_data
#   for researcher without can_view_all... perms
