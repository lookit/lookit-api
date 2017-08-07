from collections import OrderedDict
from django.db.models import Q

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from guardian.shortcuts import get_objects_for_user
from accounts.models import Child, DemographicData, Organization, User
from accounts.serializers import (ChildSerializer, DemographicDataSerializer,
                                  OrganizationSerializer, UserSerializer)
from django_filters import rest_framework as filters
from rest_framework_json_api import views
from studies.models import Response, Study
from studies.serializers import (ResponseWriteableSerializer, ResponseSerializer,
                                 StudySerializer)


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
    resource_name = 'organizations'
    lookup_field = 'uuid'
    queryset = Organization.objects.all()
    serializer_class = OrganizationSerializer
    filter_fields = [('study', 'study'), ('user', 'user'), ]
    http_method_names = ['get', 'head', 'options']
    permission_classes = [IsAuthenticated]


class ChildViewSet(FilterByUrlKwargsMixin, views.ModelViewSet):
    resource_name = 'children'
    queryset = Child.objects.filter(user__is_researcher=False, user__is_active=True).distinct()
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
        studies = get_objects_for_user(self.request.user, 'studies.can_view_study_responses')
        study_ids = studies.values_list('id', flat=True)
        return Child.objects.filter(Q(response__study__id__in=study_ids) | Q(user__id=self.request.user.id)).distinct()


class DemographicDataViewSet(FilterByUrlKwargsMixin, views.ModelViewSet):
    lookup_field = 'uuid'
    resource_name = 'demographics'
    # TODO modify when oauth in
    queryset = DemographicData.objects.filter(user__is_active=True)
    serializer_class = DemographicDataSerializer
    filter_fields = [('user', 'user'), ]
    http_method_names = ['get', 'head', 'options']
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        """
        Overrides queryset.

        Shows 1) demographics attached to responses you can view, and 2) your own demographics
        """
        studies = get_objects_for_user(self.request.user, 'studies.can_view_study_responses')
        study_ids = studies.values_list('id', flat=True)
        return DemographicData.objects.filter(Q(response__study__id__in=study_ids) | Q(user__id=self.request.user.id)).distinct()


class UserViewSet(FilterByUrlKwargsMixin, views.ModelViewSet):
    lookup_field = 'uuid'
    resource_name = 'users'
    queryset = User.objects.filter(is_researcher=False).distinct()
    serializer_class = UserSerializer
    filter_fields = [('child', 'children'), ('response', 'responses'), ]
    http_method_names = ['get', 'head', 'options']
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        """
        Overrides queryset.

        Shows 1) users that have responded to studies you can view and 2) your own user object
        """
        # TODO should we further restrict on participants only?
        studies = get_objects_for_user(self.request.user, 'studies.can_view_study_responses')
        study_ids = studies.values_list('id', flat=True)
        return User.objects.filter(Q(children__response__study__id__in=study_ids) | Q(id=self.request.user.id)).distinct()

class StudyViewSet(FilterByUrlKwargsMixin, views.ModelViewSet):
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
    resource_name = 'responses'
    queryset = Response.objects.all()
    serializer_class = ResponseSerializer
    lookup_field = 'uuid'
    filter_fields = [('study', 'study'), ]
    filter_backends = (filters.DjangoFilterBackend,)
    filter_class = ResponseFilter
    http_method_names = ['get', 'post', 'put', 'patch', 'head', 'options']
    permission_classes = [IsAuthenticated]

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
        studies = get_objects_for_user(self.request.user, 'studies.can_view_study_responses')
        study_ids = studies.values_list('id', flat=True)
        children_ids = Child.objects.filter(user__id=self.request.user.id).values_list('id', flat=True)
        return Response.objects.filter(Q(study__id__in=study_ids) | Q(child__id__in=children_ids)).distinct()
