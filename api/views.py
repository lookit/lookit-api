from rest_framework import viewsets

from accounts.models import DemographicData
from accounts.serializers import DemographicDataSerializer


class DemographicDataViewSet(viewsets.ModelViewSet):
    queryset = DemographicData.objects.all()
    serializer_class = DemographicDataSerializer
