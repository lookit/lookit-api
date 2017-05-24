from rest_framework_json_api import serializers
from studies.models import Study


class StudySerializer(serializers.ModelSerializer):

    class Meta:
        model = Study
        fields = '__all__'
