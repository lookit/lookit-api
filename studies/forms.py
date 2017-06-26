from ace_overlay.widgets import AceOverlayWidget
from django import forms

from studies.models import Response, Study


class ResponseForm(forms.ModelForm):
    results = forms.CharField(widget=AceOverlayWidget(mode='json', wordwrap=True, theme='textmate', width="100%", height="100%", showprintmargin=False), required=False)
    class Meta:
        fields = (
            'study',
            "child",
            'demographic_snapshot',
            'results'
        )
        model = Response


class StudyForm(forms.ModelForm):
    blocks = forms.CharField(widget=AceOverlayWidget(mode='json', wordwrap=True, theme='textmate', width="100%", height="100%", showprintmargin=False), required=False)

    class Meta:
        fields = (
            'name',
            'organization',
            'blocks'
        )
        model = Study


class StudyEditForm(forms.ModelForm):
    class Meta:
        model = Study
        fields = ['name', 'image', 'short_description', 'long_description', 'exit_url', 'criteria', 'min_age', 'max_age', 'contact_info', 'public']
        labels = {
            'short_description': "Short Description",
            'long_description': "Purpose",
            'exit_url': "Exit URL",
            'criteria': "Participant Eligibility",
            'min_age': "Minimum Age",
            'max_age': "Maximum Age",
            'contact_info': "Researcher/Contact Information",
            'public': "Discoverable"
        }
