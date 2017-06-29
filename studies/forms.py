from ace_overlay.widgets import AceOverlayWidget
from django.forms import ModelForm, Textarea
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


class StudyEditForm(forms.ModelForm):
    class Meta:
        model = Study
        fields = ['name', 'image', 'short_description', 'long_description', 'exit_url', 'criteria', 'min_age', 'max_age', 'duration', 'contact_info', 'public']
        labels = {
            'short_description': "Short Description",
            'long_description': "Purpose",
            'exit_url': "Exit URL",
            'criteria': "Participant Eligibility",
            'min_age': "Minimum Age",
            'max_age': "Maximum Age",
            'contact_info': "Researcher/Contact Information",
            'public': "Discoverable - Do you want this study to be publicly discoverable on Lookit once approved?"
        }
        widgets = {
            'short_description': Textarea(attrs={'rows': 2}),
            'long_description': Textarea(attrs={'rows': 2}),
            'exit_url': Textarea(attrs={'rows': 1}),
            'criteria': Textarea(attrs={'rows': 1}),
            'min_age': Textarea(attrs={'rows': 1}),
            'max_age': Textarea(attrs={'rows': 1}),
            'duration': Textarea(attrs={'rows': 1}),
            'contact_info': Textarea(attrs={'rows': 1}),
        }
        
class StudyForm(StudyEditForm):
    blocks = forms.CharField(widget=AceOverlayWidget(mode='json', wordwrap=True, theme='textmate', width="100%", height="100%", showprintmargin=False), required=False)
