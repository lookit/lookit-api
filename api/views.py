from collections import OrderedDict
from django.db.models import Q

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404
from guardian.shortcuts import get_objects_for_user
from accounts.models import Child, DemographicData, Organization, User
from accounts.serializers import (ChildSerializer, DemographicDataSerializer,
                                  OrganizationSerializer, UserSerializer)
from django_filters import rest_framework as filters
from rest_framework_json_api import views
from api.permissions import FeedbackPermissions, ResponsePermissions
from studies.models import Response, Study, Feedback
from studies.serializers import (ResponseWriteableSerializer, ResponseSerializer,
                                 StudySerializer, FeedbackSerializer)


class FilterByUrlKwargsMixin(views.ModelViewSet):
    filter_fields = []

    def get_queryset(self):
        '''
        Relies on a filter_fields class property to filter the queryset dynamically
        based on the kwargs passed to nested views.

        e.g. /responses/{response_uuid}/study/ should show the study tied to
        a response with {response_uuid}
        '''
        qs = super().get_queryset()
        for singular, plural in self.filter_fields:
            kwarg_key = f'{singular}_uuid'
            qs_key = f'{plural}__uuid'
            if kwarg_key in self.kwargs:
                qs = qs.filter(**{qs_key: self.kwargs.get(kwarg_key)})
        return qs


class OrganizationViewSet(FilterByUrlKwargsMixin, views.ModelViewSet):
    """
    Allows viewing a list of all organziations or retrieving a single organization
    """
    resource_name = 'organizations'
    lookup_field = 'uuid'
    queryset = Organization.objects.all()
    serializer_class = OrganizationSerializer
    filter_fields = [('study', 'study'), ('user', 'user'), ]
    http_method_names = ['get', 'head', 'options']
    permission_classes = [IsAuthenticated]


class ChildViewSet(FilterByUrlKwargsMixin, views.ModelViewSet):
    """
    Allows viewing a list of all children you have permission to view or retrieving a single child.

    You can view data from children that have responded to studies that you have permission to view, as well as view any of your own children that you have registered.
    """
    resource_name = 'children'
    queryset = Child.objects.filter(user__is_active=True).distinct()
    serializer_class = ChildSerializer
    lookup_field = 'uuid'
    filter_fields = [('user', 'user'), ]
    http_method_names = ['get', 'head', 'options']
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        """
        Overrides queryset.

        Show children that have 1) responded to studies you can view and 2) are your own children
        """
        qs_ids = super().get_queryset().values_list('id', flat=True)
        studies = get_objects_for_user(self.request.user, 'studies.can_view_study_responses')
        study_ids = studies.values_list('id', flat=True)
        return qs_ids.model.objects.filter((Q(response__study__id__in=study_ids) | Q(user__id=self.request.user.id)), (Q(id__in=qs_ids))).distinct()


class DemographicDataViewSet(ChildViewSet):
    """
    Allows viewing a list of all demographic data you have permission to view as well as your own demographic data.
    """
    resource_name = 'demographics'
    queryset = DemographicData.objects.filter(user__is_active=True)
    serializer_class = DemographicDataSerializer
    filter_fields = [('user', 'user'), ]


class UserViewSet(FilterByUrlKwargsMixin, views.ModelViewSet):
    """
    Allows viewing a list of all users you have permission to view or retrieving a single user.

    You can view participants that have responded to studies you have permission to view, as well as own user information
    """
    lookup_field = 'uuid'
    resource_name = 'users'
    queryset = User.objects.all()
    serializer_class = UserSerializer
    filter_fields = [('child', 'children'), ('response', 'responses'), ]
    http_method_names = ['get', 'head', 'options']
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        """
        Overrides queryset.

        Shows 1) users that have responded to studies you can view and 2) your own user object
        """
        qs_ids = super().get_queryset().values_list('id', flat=True)
        studies = get_objects_for_user(self.request.user, 'studies.can_view_study_responses')
        study_ids = studies.values_list('id', flat=True)
        return User.objects.filter((Q(children__response__study__id__in=study_ids) | Q(id=self.request.user.id)), Q(id__in=qs_ids)).distinct()

class StudyViewSet(FilterByUrlKwargsMixin, views.ModelViewSet):
    """
    Allows viewing a list of studies or retrieivng a single study

    You can view studies that are active as well as studies you have permission to edit.
    """
    resource_name = 'studies'
    queryset = Study.objects.filter(state='active')
    serializer_class = StudySerializer
    lookup_field = 'uuid'
    filter_fields = [('response', 'responses'), ]
    http_method_names = ['get', 'head', 'options']
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        """
        Shows studies that are either 1) active or 2) studies you have permission to edit.

        "can_edit_study" permissions allows the researcher to preview the study before it has been made active/public
        """
        qs = super().get_queryset()
        # List View restricted to public.  Detail view can show a private or public study.
        if 'List' in self.get_view_name():
            qs = qs.filter(public=True)

        return (qs | get_objects_for_user(self.request.user, 'studies.can_edit_study')).distinct()

class ResponseFilter(filters.FilterSet):
    child = filters.UUIDFilter(name='child__uuid')

    class Meta:
        model = Response
        fields = ['child']


class ResponseViewSet(FilterByUrlKwargsMixin, views.ModelViewSet):
    """
    Allows viewing a list of responses, retrieving a response, creating a response, or updating a response.

    You can view responses to studies that you have permission to view, or responses by your own children.
    """
    resource_name = 'responses'
    queryset = Response.objects.all()
    serializer_class = ResponseSerializer
    lookup_field = 'uuid'
    filter_fields = [('study', 'study'), ]
    filter_backends = (filters.DjangoFilterBackend,)
    filter_class = ResponseFilter
    http_method_names = ['get', 'post', 'put', 'patch', 'head', 'options']
    permission_classes = [IsAuthenticated, ResponsePermissions]

    def get_serializer_class(self):
         """Return a different serializer for create views"""
         if self.action == 'create':
             return ResponseWriteableSerializer
         return super().get_serializer_class()

    def get_queryset(self):
        """
        Overrides queryset.

        Shows responses that you either have permission to view, or responses by your own children
        """

        children_ids = Child.objects.filter(user__id=self.request.user.id).values_list('id', flat=True)

        # if this viewset is accessed via the 'study-responses' route,
        # it wll have been passed the `study_uuid` kwarg and the queryset
        # needs to be filtered accordingly; if it was accessed via the
        # unnested '/responses' route, the queryset should include all responses you can view
        if 'study_uuid' in self.kwargs:
            study_uuid = self.kwargs['study_uuid']
            queryset = Response.objects.filter(study__uuid=study_uuid)
            if self.request.user.has_perm('studies.can_view_study_responses', get_object_or_404(Study, uuid=study_uuid)):
                return queryset
            else:
                return queryset.filter(child__id__in=children_ids)

        studies = get_objects_for_user(self.request.user, 'studies.can_view_study_responses')
        study_ids = studies.values_list('id', flat=True)
        return Response.objects.filter(Q(study__id__in=study_ids) | Q(child__id__in=children_ids)).distinct()


class FeedbackViewSet(FilterByUrlKwargsMixin, views.ModelViewSet):
    """
    Allows viewing a list of feedback, retrieving a single piece of feedback, or creating feedback.

    You can view feedback on studies you have permission to edit, as well as feedback left on your responses.

    """
    resource_name = 'feedback'
    queryset = Feedback.objects.all()
    serializer_class = FeedbackSerializer
    lookup_field = 'uuid'
    http_method_names = ['get', 'post', 'put', 'patch', 'head', 'options']
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
        study_ids = get_objects_for_user(self.request.user, 'studies.can_edit_study').values_list('id', flat=True)
        return qs.filter(Q(response__study__id__in=study_ids) | Q(response__child__user=self.request.user)).distinct()
