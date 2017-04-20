from django import forms

from accounts.models import Collaborator, User
from studies.models import Study


class UserForm(forms.ModelForm):
    class Meta:
        model = User
        exclude = ('password', )


class CollaboratorStudiesForm(forms.Form):
    collaborator = forms.ModelChoiceField(Collaborator.objects.all(), required=True, label='Collaborator')
    studies = forms.ModelMultipleChoiceField(Study.objects.all(), required=True, label='Assigned Studies')
    def __init__(self, *args, **kwargs):
        self.collaborator = kwargs.pop('instance')
        super(CollaboratorStudiesForm, self).__init__(*args, **kwargs)
