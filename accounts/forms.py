from django import forms

from accounts.models import User
from studies.models import Study


class UserForm(forms.ModelForm):
    class Meta:
        model = User
        exclude = ('password', )


class UserStudiesForm(forms.Form):
    template = 'accounts/collaborator_form.html'
    user = forms.ModelChoiceField(User.objects.all(), required=True, label='Collaborator')
    studies = forms.ModelMultipleChoiceField(Study.objects.all(), required=True, label='Assigned Studies')
    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('instance')
        super(UserStudiesForm, self).__init__(*args, **kwargs)
