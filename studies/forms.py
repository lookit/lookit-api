from ace_overlay.widgets import AceOverlayWidget
from django import forms

from studies.models import Response


class ResponseForm(forms.ModelForm):
    results = forms.CharField(widget=AceOverlayWidget(mode='json', wordwrap=True, theme='textmate', width="100%", height="100%", showprintmargin=False), required=False)
    class Meta:
        fields = (
            'study',
            'participant',
            'demographic_snapshot',
            'results'
        )
        model = Response
