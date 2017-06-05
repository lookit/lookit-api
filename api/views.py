from accounts.models import DemographicData, Profile, User
from accounts.serializers import (DemographicDataSerializer, ProfileSerializer,
                                  UserSerializer)
from rest_framework_json_api import views
from studies.models import Study
from studies.serializers import StudySerializer


class ProfileViewSet(views.ModelViewSet):
    queryset = Profile.objects.filter(user__demographics__isnull=False, user__is_active=True)
    serializer_class = ProfileSerializer
    lookup_field = 'uuid'


class ProfileDemographicsViewSet(views.ModelViewSet):
    queryset = DemographicData.objects.all()
    serializer_class = DemographicDataSerializer

    def get_queryset(self, *args, **kwargs):
        qs = super().get_queryset(*args, **kwargs)
        return qs.filter(user__profiles__uuid=self.kwargs['profile_id'])


class UserViewSet(views.ModelViewSet):
    lookup_field = 'uuid'
    resource_name = 'users'
    queryset = User.objects.filter(demographics__isnull=False)
    serializer_class = UserSerializer


class StudyViewSet(views.ModelViewSet):
    queryset = Study.objects.filter(state='active')
    serializer_class = StudySerializer
