from rest_framework import viewsets

from accounts.models import User
from accounts.serializers import ParticipantSerializer


class ParticipantViewSet(viewsets.ModelViewSet):
    queryset = User.objects.filter(participant__isnull=False)
    serializer_class = ParticipantSerializer
