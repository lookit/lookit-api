from rest_framework import viewsets

from accounts.models import DemographicData
from accounts.serializers import DemographicDataSerializer
from studies.models import Study
from studies.serializers import StudySerializer


class DemographicDataViewSet(viewsets.ModelViewSet):
    queryset = DemographicData.objects.all()
    serializer_class = DemographicDataSerializer


class StudyViewSet(viewsets.ModelViewSet):
    queryset = Study.objects.filter(state='active')
    serializer_class = StudySerializer
