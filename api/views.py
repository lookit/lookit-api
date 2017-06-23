from accounts.models import Child, DemographicData, User
from accounts.serializers import (ChildSerializer, DemographicDataSerializer,
                                  UserSerializer)
from rest_framework_json_api import views
from studies.models import Response, Study
from studies.serializers import ResponseSerializer, StudySerializer


class ChildViewSet(views.ModelViewSet):
    resource_name = 'children'
    queryset = Child.objects.filter(user__demographics__isnull=False, user__is_active=True)
    serializer_class = ChildSerializer
    lookup_field = 'uuid'


class DemographicDataViewSet(views.ModelViewSet):
    lookup_field = 'uuid'
    resource_name = 'demographics'
    queryset = DemographicData.objects.filter(user__is_active=True)
    serializer_class = DemographicDataSerializer


class UserViewSet(views.ModelViewSet):
    lookup_field = 'uuid'
    resource_name = 'users'
    queryset = User.objects.filter(demographics__isnull=False)
    serializer_class = UserSerializer


class StudyViewSet(views.ModelViewSet):
    queryset = Study.objects.filter(state='active')
    serializer_class = StudySerializer
    lookup_field = 'uuid'

class ResponseViewSet(views.ModelViewSet):
    queryset = Response.objects.all()
    serializer_class = ResponseSerializer
    lookup_field = 'uuid'
