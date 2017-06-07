from ace_overlay.widgets import AceOverlayWidget
from django import forms

from studies.models import Response, Study


class ResponseForm(forms.ModelForm):
    results = forms.CharField(widget=AceOverlayWidget(mode='json', wordwrap=True, theme='textmate', width="100%", height="100%", showprintmargin=False), required=False)
    class Meta:
        fields = (
            'study',
            'profile',
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
