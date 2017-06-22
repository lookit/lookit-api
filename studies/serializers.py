from api.serializers import UUIDSerializerMixin, ModelSerializer
from studies.models import Study


class StudySerializer(UUIDSerializerMixin, ModelSerializer):

    class Meta:
        model = Study
        fields = '__all__'
