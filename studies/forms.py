import json

from django import forms
from django.forms import ModelForm, Textarea

from ace_overlay.widgets import AceOverlayWidget
from studies.models import Response, Study


class ResponseForm(forms.ModelForm):
    results = forms.CharField(widget=AceOverlayWidget(mode='json', wordwrap=True, theme='textmate', width='100%', height='100%', showprintmargin=False), required=False)
    class Meta:
        fields = (
            'study',
            'child',
            'demographic_snapshot',
            'results'
        )
        model = Response


class StudyEditForm(forms.ModelForm):
    class Meta:
        model = Study
        fields = ['name', 'image', 'short_description', 'long_description', 'exit_url', 'criteria', 'min_age', 'max_age', 'duration', 'contact_info', 'public']
        labels = {
            'short_description': 'Short Description',
            'long_description': 'Purpose',
            'exit_url': 'Exit URL',
            'criteria': 'Participant Eligibility',
            'min_age': 'Minimum Age',
            'max_age': 'Maximum Age',
            'contact_info': 'Researcher/Contact Information',
            'public': 'Discoverable - Do you want this study to be publicly discoverable on Lookit once activated?'
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

        help_texts = {
            'image': 'Please keep your file size less than 1 MB',
            'exit_url': "Specify the page where you want to send your participants after they've completed the study.",
            'short_description': 'Give your study a description here.',
            'long_description': 'Explain the purpose of your study here.',
            'min_age': 'Units please, e.g. 1 month or 1 year',
            'max_age': 'Units please, e.g. 3 months or 3 years'
        }

class StudyForm(forms.ModelForm):
    structure = forms.CharField(label='Build Study - Add JSON', widget=AceOverlayWidget(mode='json', wordwrap=True, theme='textmate', width='100%', height='100%', showprintmargin=False), required=False, help_text='Add the frames of your study as well as the sequence of those frames.  This can be added later.')

    def clean_structure(self):
         structure = self.cleaned_data['structure']
         try:
             json_data = json.loads(structure) #loads string as json
         except:
             raise forms.ValidationError("Invalid JSON")
         return json_data

    class Meta:
        model = Study
        fields = ['name', 'image', 'short_description', 'long_description', 'exit_url', 'criteria', 'min_age', 'max_age', 'duration', 'contact_info', 'public', 'structure', 'study_type']
        labels = {
            'short_description': 'Short Description',
            'long_description': 'Purpose',
            'exit_url': 'Exit URL',
            'criteria': 'Participant Eligibility',
            'min_age': 'Minimum Age',
            'max_age': 'Maximum Age',
            'contact_info': 'Researcher/Contact Information',
            'public': 'Discoverable - Do you want this study to be publicly discoverable on Lookit once activated?',
            'study_type': 'Study Type'
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
        help_texts = {
            'image': 'Please keep your file size less than 1 MB',
            'exit_url': "Specify the page where you want to send your participants after they've completed the study.",
            'short_description': 'Give your study a description here.',
            'long_description': 'Explain the purpose of your study here.',
            'study_type': "Specify the build process as well as the parameters needed by the experiment builder. If you don't know what this is, just select the default.",
            'min_age': 'Units please, e.g. 1 month or 1 year',
            'max_age': 'Units please, e.g. 3 months or 3 years'
        }

class StudyBuildForm(forms.ModelForm):
    structure = forms.CharField(label='Build Study - Add JSON', widget=AceOverlayWidget(mode='json', wordwrap=True, theme='textmate', width='100%', height='100%', showprintmargin=False), required=False, help_text='Add the frames of your study as well as the sequence of those frames.')

    def clean_structure(self):
         structure = self.cleaned_data['structure']
         try:
             json_data = json.loads(structure) #loads string as json
         except:
             raise forms.ValidationError("Invalid JSON")
         return json_data

    class Meta:
        model = Study
        fields = ['structure']
