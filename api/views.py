from accounts.models import Child, DemographicData, Organization, User
from accounts.serializers import (ChildSerializer, DemographicDataSerializer,
                                  OrganizationSerializer, UserSerializer)
from rest_framework_json_api import views
from studies.models import Response, Study
from studies.serializers import ResponseSerializer, StudySerializer


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


class ChildViewSet(FilterByUrlKwargsMixin, views.ModelViewSet):
    resource_name = 'children'
    queryset = Child.objects.filter(user__demographics__isnull=False, user__is_active=True)
    serializer_class = ChildSerializer
    lookup_field = 'uuid'
    filter_fields = [('user', 'user'), ]


class DemographicDataViewSet(FilterByUrlKwargsMixin, views.ModelViewSet):
    lookup_field = 'uuid'
    resource_name = 'demographics'
    queryset = DemographicData.objects.filter(user__is_active=True)
    serializer_class = DemographicDataSerializer
    filter_fields = [('user', 'user'), ]


class UserViewSet(FilterByUrlKwargsMixin, views.ModelViewSet):
    lookup_field = 'uuid'
    resource_name = 'users'
    queryset = User.objects.filter(demographics__isnull=False)
    serializer_class = UserSerializer
    filter_fields = [('child', 'children'), ('response', 'responses'), ]


class StudyViewSet(FilterByUrlKwargsMixin, views.ModelViewSet):
    resource_name = 'studies'
    queryset = Study.objects.filter(state='active')
    serializer_class = StudySerializer
    lookup_field = 'uuid'
    filter_fields = [('response', 'responses'), ]


class ResponseViewSet(FilterByUrlKwargsMixin, views.ModelViewSet):
    resource_name = 'responses'
    queryset = Response.objects.all()
    serializer_class = ResponseSerializer
    lookup_field = 'uuid'
    filter_fields = [('study', 'study'), ]
