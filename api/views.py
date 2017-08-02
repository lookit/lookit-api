from collections import OrderedDict

from rest_framework import status
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
    http_method_names = [u'get', u'head', u'options']


class ChildViewSet(FilterByUrlKwargsMixin, views.ModelViewSet):
    resource_name = 'children'
    queryset = Child.objects.filter(user__demographics__isnull=False, user__is_active=True).distinct()
    serializer_class = ChildSerializer
    lookup_field = 'uuid'
    filter_fields = [('user', 'user'), ]
    http_method_names = [u'get', u'head', u'options']


class DemographicDataViewSet(FilterByUrlKwargsMixin, views.ModelViewSet):
    lookup_field = 'uuid'
    resource_name = 'demographics'
    queryset = DemographicData.objects.filter(user__is_active=True)
    serializer_class = DemographicDataSerializer
    filter_fields = [('user', 'user'), ]
    http_method_names = [u'get', u'head', u'options']


class UserViewSet(FilterByUrlKwargsMixin, views.ModelViewSet):
    lookup_field = 'uuid'
    resource_name = 'users'
    queryset = User.objects.filter(demographics__isnull=False).distinct()
    serializer_class = UserSerializer
    filter_fields = [('child', 'children'), ('response', 'responses'), ]
    http_method_names = [u'get', u'head', u'options']


class StudyViewSet(FilterByUrlKwargsMixin, views.ModelViewSet):
    resource_name = 'studies'
    queryset = Study.objects.filter(state='active', public=True)
    serializer_class = StudySerializer
    lookup_field = 'uuid'
    filter_fields = [('response', 'responses'), ]
    http_method_names = [u'get', u'head', u'options']

    def get_queryset(self):
        """
        Shows studies that are either 1) active and public or 2) studies you have permission to view.

        "can_view_study" permissions allows the researcher to preview the study before it has been made active/public
        """
        return (super().get_queryset() | get_objects_for_user(self.request.user, 'studies.can_view_study')).distinct()

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
    http_method_names = [u'get', u'post', u'put', u'patch', u'head', u'options']

    def get_serializer_class(self):
        """Return a different serializer for create views"""
        if self.action == 'create':
            return ResponseWriteableSerializer
        return super().get_serializer_class()
