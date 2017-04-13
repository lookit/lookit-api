from accounts.models import ParticipantProfile, User
from rest_framework_json_api import serializers


class ParticipantSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ('username', )
