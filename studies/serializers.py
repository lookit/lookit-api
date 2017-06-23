from api.serializers import ModelSerializer, UUIDSerializerMixin
from studies.models import Response, Study


class StudySerializer(UUIDSerializerMixin, ModelSerializer):

    class Meta:
        model = Study
        fields = '__all__'


class ResponseSerializer(UUIDSerializerMixin, ModelSerializer):

    class Meta:
        model = Response
        fields = '__all__'
