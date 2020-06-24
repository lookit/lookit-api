from django.db.models import Q
from django.shortcuts import get_object_or_404
from django_filters import rest_framework as filters
from guardian.shortcuts import get_objects_for_user
from rest_framework.filters import OrderingFilter
from rest_framework.permissions import IsAuthenticated
from rest_framework_json_api import views

from accounts.models import Child, DemographicData, User
from accounts.serializers import (
    BasicUserSerializer,
    ChildSerializer,
    DemographicDataSerializer,
    FullUserSerializer,
    LabSerializer,
)
from api.permissions import FeedbackPermissions, ResponsePermissions
from studies.models import Feedback, Lab, Response, Study
from studies.permissions import StudyPermission
from studies.queries import get_consented_responses_qs, studies_for_which_user_has_perm
from studies.serializers import (
    FeedbackSerializer,
    ResponseSerializer,
    ResponseWriteableSerializer,
    StudySerializer,
)

CONVERSION_TYPES = {
    "child": Child,
    "study": Study,
    "response": Response,
    "feedback": Feedback,
    "user": User,
}


class FilterByUrlKwargsMixin(views.ModelViewSet):
    filter_fields = []

    def get_queryset(self):
        """
        Relies on a filter_fields class property to filter the queryset dynamically
        based on the kwargs passed to nested views.

        e.g. /responses/{response_uuid}/study/ should show the study tied to
        a response with {response_uuid}
        """
        qs = super().get_queryset()
        for singular, plural in self.filter_fields:
            kwarg_key = f"{singular}_uuid"
            qs_key = f"{plural}__uuid"
            if kwarg_key in self.kwargs:
                qs = qs.filter(**{qs_key: self.kwargs.get(kwarg_key)})
        return qs


class ConvertUuidToIdMixin(views.ModelViewSet):
    """Utility mixin to bridge the ID <--> UUID gap in the frontend.

    This is obviously a wonky solution, but it's far better than copying and pasting and version-locking
    the codebase.
    """

    def initial(self, request, *args, **kwargs):
        """Do regular initialize, except replace id fields with UUID."""
        if self.action in ("create", "partial_update"):
            # find things in request.data
            for prop, value in request.data.items():
                if value and isinstance(value, dict) and value.get("id", None):
                    value["id"] = get_object_or_404(
                        CONVERSION_TYPES[prop], uuid=value["id"]
                    ).id

        super().initial(request, *args, **kwargs)


class LabViewSet(FilterByUrlKwargsMixin, views.ModelViewSet):
    """
    Allows viewing a list of all approved labs or retrieving a single lab
    """

    resource_name = "labs"
    lookup_field = "uuid"
    queryset = Lab.objects.filter(approved_to_test=True)
    serializer_class = LabSerializer
    filter_fields = [("study", "study"), ("user", "user")]
    http_method_names = ["get", "head", "options"]
    permission_classes = [IsAuthenticated]


class ChildViewSet(FilterByUrlKwargsMixin, views.ModelViewSet):
    """
    Allows viewing a list of all children you have permission to view or retrieving a single child.

    You can view data from children that have responded to studies that you have permission to view, as well as view any of your own children that you have registered.
    """

    resource_name = "children"
    queryset = Child.objects.filter(user__is_active=True)
    serializer_class = ChildSerializer
    lookup_field = "uuid"
    filter_fields = [("user", "user")]
    http_method_names = ["get", "head", "options"]
    permission_classes = [IsAuthenticated]
    filter_backends = (OrderingFilter,)
    ordering_fields = ("birthday",)

    def get_queryset(self):
        """
        Overrides queryset.

        Show children that have 1) responded to studies you can view and 2) are your own children
        """
        children_for_active_users = super().get_queryset()
        # Users with can_read_all_user_data permissions can view all children/demographics of active users via the API
        if self.request.user.has_perm("accounts.can_read_all_user_data"):
            return children_for_active_users

        # TODO: make helper for this, maybe on user
        studies_for_data = studies_for_which_user_has_perm(
            self.request.user, StudyPermission.READ_STUDY_RESPONSE_DATA
        ).values_list("id", flat=True)
        studies_for_preview = studies_for_which_user_has_perm(
            self.request.user, StudyPermission.READ_STUDY_PREVIEW_DATA
        ).values_list("id", flat=True)
        consented_responses = get_consented_responses_qs().filter(
            (Q(study__id__in=studies_for_data) & Q(is_preview=False))
            | (Q(study__id__in=studies_for_preview) & Q(is_preview=True))
        )

        child_ids = consented_responses.values_list("child", flat=True)

        return children_for_active_users.filter(
            (Q(id__in=child_ids) | Q(user__id=self.request.user.id))
        )


class DemographicDataViewSet(FilterByUrlKwargsMixin, views.ModelViewSet):
    """
    Allows viewing a list of all demographic data you have permission to view as well as your own demographic data.
    """

    resource_name = "demographics"
    queryset = DemographicData.objects.filter(user__is_active=True)
    serializer_class = DemographicDataSerializer
    lookup_field = "uuid"
    filter_fields = [("user", "user")]
    http_method_names = ["get", "head", "options"]
    permission_classes = [IsAuthenticated]
    filter_backends = (OrderingFilter,)

    def get_queryset(self):
        """Queryset getter override.

        Largely duplicated from ChildViewSet but not completely, so we should duplicate before introducing the wrong
        abstraction.

        :return: The properly configured queryset.
        """
        demographics_for_active_users = super().get_queryset()

        if self.request.user.has_perm("accounts.can_read_all_user_data"):
            return demographics_for_active_users

        studies_for_data = studies_for_which_user_has_perm(
            self.request.user, StudyPermission.READ_STUDY_RESPONSE_DATA
        ).values_list("id", flat=True)
        studies_for_preview = studies_for_which_user_has_perm(
            self.request.user, StudyPermission.READ_STUDY_PREVIEW_DATA
        ).values_list("id", flat=True)
        consented_responses = get_consented_responses_qs().filter(
            (Q(study__id__in=studies_for_data) & Q(is_preview=False))
            | (Q(study__id__in=studies_for_preview) & Q(is_preview=True))
        )

        demographics_ids = consented_responses.values_list(
            "demographic_snapshot", flat=True
        )

        return demographics_for_active_users.filter(
            (Q(id__in=demographics_ids) | Q(user__id=self.request.user.id))
        )


class UserViewSet(FilterByUrlKwargsMixin, views.ModelViewSet):
    """
    Allows viewing a list of all users you have permission to view or retrieving a single user.

    You can view participants that have responded to studies you have permission to view, as well as own user information
    """

    lookup_field = "uuid"
    resource_name = "users"
    queryset = User.objects.all()
    filter_fields = [("child", "children"), ("response", "responses")]
    http_method_names = ["get", "head", "options"]
    permission_classes = [IsAuthenticated]

    def get_serializer_class(self):
        # Use full user serializer (with username data, etc.) iff user has permissions to view all accounts
        if self.request.user.has_perm("accounts.can_read_usernames"):
            return FullUserSerializer
        return BasicUserSerializer

    def get_queryset(self):
        """
        Overrides queryset.

        Shows 1) users that have responded to studies you can view and 2) your own user object
        """
        all_users = super().get_queryset()
        # Users with can_read_all_user_data permissions can view all active users via the API
        if self.request.user.has_perm("accounts.can_read_all_user_data"):
            return all_users.filter(is_active=True)
        qs_ids = all_users.values_list("id", flat=True)

        studies_for_data = studies_for_which_user_has_perm(
            self.request.user, StudyPermission.READ_STUDY_RESPONSE_DATA
        ).values_list("id", flat=True)
        studies_for_preview = studies_for_which_user_has_perm(
            self.request.user, StudyPermission.READ_STUDY_PREVIEW_DATA
        ).values_list("id", flat=True)
        consented_responses = get_consented_responses_qs().filter(
            (Q(study__id__in=studies_for_data) & Q(is_preview=False))
            | (Q(study__id__in=studies_for_preview) & Q(is_preview=True))
        )

        child_ids = consented_responses.values_list("child", flat=True)
        return User.objects.filter(
            (Q(children__id__in=child_ids) | Q(id=self.request.user.id)),
            Q(id__in=qs_ids),
        ).distinct()


class StudyViewSet(FilterByUrlKwargsMixin, views.ModelViewSet):
    """
    Allows viewing a list of studies or retrieving a single study
    """

    resource_name = "studies"
    queryset = Study.objects.filter(state="active")
    serializer_class = StudySerializer
    lookup_field = "uuid"
    filter_fields = [("response", "responses")]
    http_method_names = ["get", "head", "options"]
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        """
        In general: all active studies.
        List view: only public studies.
        Researchers: also include any studies the researcher can preview
        """
        qs = Study.objects.filter(state="active")
        # List View restricted to public.  Detail view can show a private or public study.
        if "List" in self.get_view_name():
            qs = qs.filter(public=True)

        # Researchers
        if self.request.user.is_researcher:
            preview_studies = Study.objects.filter(
                shared_preview=True
            ) | studies_for_which_user_has_perm(
                self.request.user, StudyPermission.READ_STUDY_DETAILS
            )
            qs = qs | preview_studies

        return qs.distinct().order_by("-date_modified")


class ResponsesFilter(filters.FilterSet):
    """A Response filter that actually works."""

    child = filters.UUIDFilter(field_name="child__uuid")
    study = filters.UUIDFilter(field_name="study__uuid")

    class Meta:
        model = Response
        fields = []


class ResponseViewSet(ConvertUuidToIdMixin, views.ModelViewSet):
    """
    Allows viewing a list of responses, retrieving a response, creating a response, or updating a response.

    You can view responses to studies that you have permission to view, or responses by your own children.
    """

    resource_name = "responses"
    queryset = Response.objects.all()
    serializer_class = ResponseSerializer
    lookup_field = "uuid"
    filterset_class = ResponsesFilter
    filter_backends = (filters.DjangoFilterBackend,)
    http_method_names = ["get", "post", "put", "patch", "head", "options"]
    permission_classes = [IsAuthenticated, ResponsePermissions]

    def get_serializer_class(self):
        """Return a different serializer for create views"""
        if self.action in ("create", "partial_update"):
            return ResponseWriteableSerializer
        return super().get_serializer_class()

    def get_queryset(self):
        """Overrides queryset.

        The overall idea is that we want to limit the responses one can retrieve through the API to two cases:
        1) A user is in a session in the frameplayer, and they're hitting the response API to update their session.
        2) A researcher is programmatically accessing the API to get responses for a given study

        XXX: HERE BE DRAGONS: this method is invoked with PATCH as well as GET requests!
        TODO: Break this out into multiple handlers. The logic-gymnastics is getting annoying.
        """
        children_belonging_to_user = Child.objects.filter(user__id=self.request.user.id)

        # NESTED ROUTE:
        # GET /api/v1/studies/{STUDY_ID}/responses/?{Query string with pagination and child id}
        # This route gets accessed by:
        #     1) Participant sessions GETting history of responses for a study and a given child.
        #     2) Experimenters/parents programmatically GETting the responses facet of the *Study*
        #        API to retrieve responses for a given study.
        if "study_uuid" in self.kwargs:
            study_uuid = self.kwargs["study_uuid"]
            study = get_object_or_404(Study, uuid=study_uuid)

            nested_responses = study.responses

            # CASE 1: Participant session, using query string with child ID.
            # Want same functionality regardless of whether user is a researcher.
            child_id = self.request.query_params.get("child", None)
            if child_id == "TEST_CHILD_DISREGARD":
                return Response.objects.none()  # Preview route
            elif child_id is not None:
                nested_responses = nested_responses.filter(
                    child__uuid=child_id, child__in=children_belonging_to_user
                )

            # CASE 2: Experimenters/parents getting responses for study.
            else:
                if self.request.user.has_study_perms(
                    StudyPermission.READ_STUDY_RESPONSE_DATA, study
                ) or self.request.user.has_study_perms(
                    StudyPermission.READ_STUDY_PREVIEW_DATA, study
                ):
                    consented_responses = study.responses_for_researcher(
                        self.request.user
                    )  # consented preview/real responses as appropriate
                    nested_responses = nested_responses.filter(
                        Q(pk__in=consented_responses)
                        | Q(child__in=children_belonging_to_user)
                    ).select_related(
                        "child",
                        "child__user",
                        "study",
                        "study__study_type",
                        "demographic_snapshot",
                    )
                else:
                    nested_responses = nested_responses.filter(
                        child__in=children_belonging_to_user
                    )

            # Order by date created even though in some edge cases the current session will
            # not be the most recently created (e.g., same user made an additional attempt to
            # participate after starting this session) - updating
            # consent status will change date_modified
            return nested_responses.order_by("-date_modified")

        else:  # NON-NESTED ROUTE
            # GET '/api/v1/responses/' or PATCH '/api/v1/responses/{RESPONSE_UUID}'.
            # This route gets accessed by:
            #     1) Participant sessions PATCHing (partial updating) ongoing response-sessions.
            #     2) Experimenters/parents programmatically GETting the Responses API

            studies_for_data = studies_for_which_user_has_perm(
                self.request.user, StudyPermission.READ_STUDY_RESPONSE_DATA
            ).values_list("id", flat=True)
            studies_for_preview = studies_for_which_user_has_perm(
                self.request.user, StudyPermission.READ_STUDY_PREVIEW_DATA
            ).values_list("id", flat=True)
            consented_responses = get_consented_responses_qs().filter(
                (Q(study__id__in=studies_for_data) & Q(is_preview=False))
                | (Q(study__id__in=studies_for_preview) & Q(is_preview=True))
            )

            response_queryset = Response.objects.filter(
                Q(child__in=children_belonging_to_user)  # Case #1
                | Q(pk__in=consented_responses)  # Case #2
            ).select_related(
                "child",
                "child__user",
                "study",
                "study__study_type",
                "demographic_snapshot",
            )

            return response_queryset.order_by("-date_modified")


class FeedbackViewSet(FilterByUrlKwargsMixin, ConvertUuidToIdMixin, views.ModelViewSet):
    """
    Allows viewing a list of feedback, retrieving a single piece of feedback, or creating feedback.

    You can view feedback on studies you have permission to edit, as well as feedback left on your responses.

    """

    resource_name = "feedback"
    queryset = Feedback.related_manager.get_queryset()
    serializer_class = FeedbackSerializer
    lookup_field = "uuid"
    http_method_names = ["get", "post", "put", "patch", "head", "options"]
    permission_classes = [IsAuthenticated, FeedbackPermissions]

    def perform_create(self, serializer):
        # Adds logged-in user as researcher on feedback
        serializer.save(researcher=self.request.user)

    def get_queryset(self):
        """
        Overrides queryset.

        Shows feedback for studies you can edit, or feedback left on your created responses.
        A researcher can only add feedback to responses to studies they have permission to
        edit feedback for.
        """
        qs = super().get_queryset()

        studies_for_data = studies_for_which_user_has_perm(
            self.request.user, StudyPermission.READ_STUDY_RESPONSE_DATA
        ).values_list("id", flat=True)
        studies_for_preview = studies_for_which_user_has_perm(
            self.request.user, StudyPermission.READ_STUDY_PREVIEW_DATA
        ).values_list("id", flat=True)
        consented_responses = get_consented_responses_qs().filter(
            (Q(study__id__in=studies_for_data) & Q(is_preview=False))
            | (Q(study__id__in=studies_for_preview) & Q(is_preview=True))
        )
        response_ids = consented_responses.values_list("id", flat=True)
        return qs.filter(
            Q(response__id__in=response_ids)
            | Q(response__child__user=self.request.user)
        ).distinct()
