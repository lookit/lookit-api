from rest_framework import viewsets

from accounts.models import ParticipantProfile
from accounts.serializers import ParticipantSerializer


class ParticipantViewSet(viewsets.ModelViewSet):
    queryset = ParticipantProfile.objects.all()
    serializer_class = ParticipantSerializer
