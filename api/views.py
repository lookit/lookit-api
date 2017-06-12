from rest_framework_json_api import views

from accounts.models import DemographicData, Child, User
from accounts.serializers import (DemographicDataSerializer, ChildSerializer,
                                  UserSerializer)
from studies.models import Study
from studies.serializers import StudySerializer


class ChildViewSet(views.ModelViewSet):
    queryset = Child.objects.filter(user__demographics__isnull=False, user__is_active=True)
    serializer_class = ChildSerializer
    lookup_field = 'uuid'


class UserViewSet(views.ModelViewSet):
    lookup_field = 'uuid'
    resource_name = 'users'
    queryset = User.objects.filter(demographics__isnull=False)
    serializer_class = UserSerializer


class StudyViewSet(views.ModelViewSet):
    queryset = Study.objects.filter(state='active')
    serializer_class = StudySerializer
