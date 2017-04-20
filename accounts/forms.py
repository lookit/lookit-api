from django import forms

from accounts.models import User
from guardian.shortcuts import assign_perm
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

    def is_valid(self):
        valid = super(UserStudiesForm, self).is_valid()
        if valid and len(self.data['studies']) > 0:
            return True

    def save(self):
        for perm in ['view_study', 'edit_study']:
            for study in self.cleaned_data['studies']:
                assign_perm(perm, self.cleaned_data['user'], study)
        return self.cleaned_data['user']
