from unittest.mock import patch

from django.test.testcases import TestCase
from django.views.generic.base import ContextMixin

from exp.views.user import ParticipantDetailView


class ParticipantDetailViewTestCase(TestCase):
    @patch.object(ParticipantDetailView, "valid_responses")
    @patch.object(ContextMixin, "get_context_data")
    def test_get_context_data_all_children(
        self, mock_super_get_context_data, mock_valid_responses
    ):
        with patch.object(ParticipantDetailView, "object", create=True), patch.object(
            ParticipantDetailView, "get_study_info"
        ):
            participant_detail_view = ParticipantDetailView()
            participant_detail_view.get_context_data()
            mock_user = mock_super_get_context_data()["user"]
            # verify that all, even soft deleted, children are queried.
            mock_user.children.filter.assert_called_once_with(
                id__in=mock_valid_responses().values_list()
            )


# TODO: ParticipantListView
# - check can only see as researcher
# - check that participant w/ consent frame completed but no consent approved does not show up
# - check that if participant has one child w/ above conditions met, and one without, the one without
#   does not show up
#
# TODO: ParticipantDetailView
# - check access as above
