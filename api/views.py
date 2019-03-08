from collections import OrderedDict

from django.db.models import Prefetch, Q, Subquery, OuterRef
from django.shortcuts import get_object_or_404
from django_filters import rest_framework as filters
from guardian.shortcuts import get_objects_for_user
from rest_framework import status
from rest_framework.exceptions import MethodNotAllowed
from rest_framework.filters import OrderingFilter
from rest_framework.permissions import IsAuthenticated
from rest_framework_json_api import views

from accounts.models import Child, DemographicData, Organization, User
from accounts.serializers import (
    BasicUserSerializer,
    ChildSerializer,
    DemographicDataSerializer,
    FullUserSerializer,
    OrganizationSerializer,
)
from api.permissions import FeedbackPermissions, ResponsePermissions
from studies.models import Feedback, Response, Study, ConsentRuling
from studies.serializers import (
    FeedbackSerializer,
    ResponseSerializer,
    ResponseWriteableSerializer,
    StudySerializer,
)


def get_consented_responses_qs():
    """Retrieve a queryset for the set of consented responses belonging to a set of studies."""
    # Create the subquery where we get the action from the most recent ruling.
    newest_ruling_subquery = Subquery(
        ConsentRuling.objects.filter(response=OuterRef("pk")).order_by("-created_at").values("action")[:1]
    )

    # Annotate that value as "current ruling" on our response queryset.
    responses_with_current_ruling = Response.objects.prefetch_related("consent_rulings").annotate(
        current_ruling=newest_ruling_subquery
    )

    # Only return the things for which our annotated property == accepted
    return responses_with_current_ruling.filter(current_ruling="accepted")


def children_for_consented_responses_only_qs():
    """Get children for consented responses only."""
    return get_consented_responses_qs().only("child")


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


class OrganizationViewSet(FilterByUrlKwargsMixin, views.ModelViewSet):
    """
    Allows viewing a list of all organizations or retrieving a single organization
    """

    resource_name = "organizations"
    lookup_field = "uuid"
    queryset = Organization.objects.all()
    serializer_class = OrganizationSerializer
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
        original_queryset = super().get_queryset()
        # Users with can_read_all_user_data permissions can view all children/demographics of active users via the API
        # if self.request.user.has_perm("accounts.can_read_all_user_data"):
        #     return original_queryset

        studies = get_objects_for_user(
            self.request.user, "studies.can_view_study_responses"
        )

        consented_responses = get_consented_responses_qs()

        return original_queryset.filter(
            (Q(response__study__in=studies) & Q(pk__in=consented_responses) | Q(user__id=self.request.user.id))
        ).distinct()


class DemographicDataViewSet(ChildViewSet):
    """
    Allows viewing a list of all demographic data you have permission to view as well as your own demographic data.
    """

    resource_name = "demographics"
    queryset = DemographicData.objects.filter(user__is_active=True)
    serializer_class = DemographicDataSerializer
    filter_fields = [("user", "user")]


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
        studies = get_objects_for_user(
            self.request.user, "studies.can_view_study_responses"
        )
        study_ids = studies.values_list("id", flat=True)
        return User.objects.filter(
            (
                Q(children__response__study__id__in=study_ids)
                | Q(id=self.request.user.id)
            ),
            Q(id__in=qs_ids),
        ).distinct()


class StudyViewSet(FilterByUrlKwargsMixin, views.ModelViewSet):
    """
    Allows viewing a list of studies or retrieivng a single study

    You can view studies that are active as well as studies you have permission to edit.
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
        Shows studies that are either 1) active or 2) studies you have permission to edit.

        "can_edit_study" permissions allows the researcher to preview the study before it has been made active/public
        """
        qs = super().get_queryset()
        # List View restricted to public.  Detail view can show a private or public study.
        if "List" in self.get_view_name():
            qs = qs.filter(public=True)

        return (
            (qs | get_objects_for_user(self.request.user, "studies.can_edit_study"))
            .distinct()
            .order_by("-date_modified")
        )


class ResponseFilter(filters.FilterSet):
    child = filters.UUIDFilter(name="child__uuid")

    class Meta:
        model = Response
        fields = ["child"]


class ResponseViewSet(FilterByUrlKwargsMixin, views.ModelViewSet):
    """
    Allows viewing a list of responses, retrieving a response, creating a response, or updating a response.

    You can view responses to studies that you have permission to view, or responses by your own children.
    """

    resource_name = "responses"
    queryset = Response.objects.all()
    serializer_class = ResponseSerializer
    lookup_field = "uuid"
    filter_fields = [("study", "study")]
    filter_backends = (filters.DjangoFilterBackend,)
    filter_class = ResponseFilter
    http_method_names = ["get", "post", "put", "patch", "head", "options"]
    permission_classes = [IsAuthenticated, ResponsePermissions]

    def get_serializer_class(self):
        """Return a different serializer for create views"""
        if self.action == "create":
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
            consented_responses = study.consented_responses
            if self.request.user.has_perm(
                "studies.can_view_study_responses",
                get_object_or_404(Study, uuid=study_uuid),
            ):
                return (
                    Response.objects.filter(
                        Q(pk__in=consented_responses)
                        | Q(child__in=children_belonging_to_user)
                    )
                    .select_related(
                        "child",
                        "child__user",
                        "study",
                        "study__study_type",
                        "demographic_snapshot",
                    )
                    .order_by("-date_modified")
                )
            else:
                return Response.objects.filter(
                    child__in=children_belonging_to_user
                ).order_by(
                    "-date_modified"
                )  # Don't need extra stuff here.
        else:  # NON-NESTED ROUTE
            # GET '/api/v1/responses/' or PATCH '/api/v1/responses/{RESPONSE_UUID}'.
            # This route gets accessed by:
            #     1) Participant sessions PATCHing (partial updating) ongoing response-sessions.
            #     2) Experimenters/parents programmatically GETting the Responses API
            viewable_studies = get_objects_for_user(
                self.request.user, "studies.can_view_study_responses"
            )

            response_queryset = Response.objects.filter(
                Q(child__in=children_belonging_to_user)  # Case #1
                | (
                    Q(study__in=viewable_studies)  # Case #2
                    & Q(pk__in=get_consented_responses_qs())
                )
            ).select_related(
                "child",
                "child__user",
                "study",
                "study__study_type",
                "demographic_snapshot",
            )

            return response_queryset.order_by("-date_modified")


class FeedbackViewSet(FilterByUrlKwargsMixin, views.ModelViewSet):
    """
    Allows viewing a list of feedback, retrieving a single piece of feedback, or creating feedback.

    You can view feedback on studies you have permission to edit, as well as feedback left on your responses.

    """

    resource_name = "feedback"
    queryset = Feedback.objects.all()
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
        A researcher can only add feedback to responses to studies they have permission to edit.
        """
        qs = super().get_queryset()
        study_ids = get_objects_for_user(
            self.request.user, "studies.can_edit_study"
        ).values_list("id", flat=True)
        return qs.filter(
            Q(response__study__id__in=study_ids)
            | Q(response__child__user=self.request.user)
        ).distinct()
