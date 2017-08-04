from django import forms
from django.contrib.auth.forms import UserCreationForm, PasswordChangeForm, UserChangeForm

from accounts.models import DemographicData, User, Child
from guardian.shortcuts import assign_perm, get_objects_for_user, remove_perm
from studies.models import Study


class UserForm(forms.ModelForm):
    class Meta:
        model = User
        exclude = ('password', )


class UserStudiesForm(forms.Form):
    template = 'accounts/researcher_form.html'
    user = forms.ModelChoiceField(User.objects.all(), required=True, label='Researcher')
    studies = forms.ModelMultipleChoiceField(
        Study.objects.all(), required=True, label='Assigned Studies')

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('instance')
        super(UserStudiesForm, self).__init__(*args, **kwargs)

    def is_valid(self):
        valid = super(UserStudiesForm, self).is_valid()
        if valid and len(self.data['studies']) > 0:
            return True

    def save(self):
        permissions = ['studies.can_view_study', 'studies.can_edit_study']
        current_permitted_objects = get_objects_for_user(self.cleaned_data['user'], permissions)
        disallowed_studies = current_permitted_objects.exclude(
            id__in=[x.id for x in self.cleaned_data['studies']])

        for perm in permissions:
            for study in self.cleaned_data['studies']:
                assign_perm(perm, self.cleaned_data['user'], study)
            for study in disallowed_studies:
                remove_perm(perm, self.cleaned_data['user'], study)
        return self.cleaned_data['user']


class ParticipantSignupForm(UserCreationForm):

    def save(self, commit=True):
        user = super(UserCreationForm, self).save(commit=False)
        user.set_password(self.cleaned_data["password1"])
        user.is_active = True
        if commit:
            user.save()
        return user

    class Meta:
        model = User
        fields = ('username', 'given_name')
        exclude = ('user_permissions', 'groups', '_identicon', 'organization',
                   'is_active', 'is_staff', 'is_superuser', 'last_login',
                   'middle_name', 'last_name')
        labels = {
            'given_name': "Username"
        }


class ParticipantUpdateForm(forms.ModelForm):
    username = forms.EmailField(disabled=True, label="Email")

    def __init__(self, *args, **kwargs):
        if 'user' in kwargs:
            kwargs.pop('user')
        super().__init__(*args, **kwargs)
        instance = getattr(self, 'instance', None)

    class Meta:
        model = User
        fields = ('username', 'given_name')
        labels = {
            'given_name': "Username"
        }


class ParticipantPasswordForm(PasswordChangeForm):
    class Meta:
        model = User


class EmailPreferencesForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ('email_next_session', 'email_new_studies', 'email_results_published', 'email_personally')
        labels = {
            'email_next_session': "It's time for another session of a study we are currently participating in",
            'email_new_studies': "A new study is available for one of my children",
            'email_results_published': "The results of a study we participated in are published",
            'email_personally': "A researcher needs to email me personally if I report a technical problem or there are questions about my responses (for example, if I reported two different birthdates for a child)."
        }


class DemographicDataForm(forms.ModelForm):
    class Meta:
        model = DemographicData
        exclude = ('created_at', 'previous', 'user', 'extra', 'uuid' )
        fields = ('country', 'state', 'density', 'languages_spoken_at_home', 'number_of_children', 'child_birthdays', 'number_of_guardians',
        'race_identification', 'age', 'gender', 'education_level', 'spouse_education_level', 'annual_income',
        'number_of_books', 'additional_comments')

        labels = {
            'country': 'What country do you live in?',
            'state': 'What state do you live in?',
            'density': 'How would you describe the area where you live?',
            'languages_spoken_at_home': 'What language(s) does your family speak at home?',
            'number_of_children': 'How many children do you have?',
            'number_of_guardians': 'How many parents/guardians do your children live with?',
            'race_identification': 'What category(ies) does your family identify as?',
            'age': "What is your age?",
            'gender': "What is your gender?",
            'education_level': "What is the highest level of education you've completed?",
            'spouse_education_level': 'What is the highest level of education your spouse has completed?',
            'annual_income': 'What is your approximate family yearly income (in US dollars)?',
            'number_of_books': "About how many children's books are there in your home?",
            'additional_comments': "Anything else you'd like us to know?"
        }

        help_texts: {
            'child_birthdays': "Please enter in comma-separated list YYYY-MM-DD, YYYY-MM-DD, YYYY-MM-DD, ... ",
            'number_of_guardians': 'If the answer varies due to shared custody arrangements or travel, please enter the number of parents/guardians your children are usually living with or explain below.'
        }
        widgets = {
            'languages_spoken_at_home': forms.Textarea(attrs={'rows': 1}),
            'additional_comments': forms.Textarea(attrs={'rows':2})
        }


class ChildForm(forms.ModelForm):
    class Meta:
        model = Child
        fields = ('given_name', 'birthday', 'gender', 'age_at_birth', 'additional_information')

        labels = {
            'given_name': 'First Name',
            'birthday': "Birthday - YYYY-MM-DD ",
            'age_at_birth': 'Gestational Age at Birth',
            'additional_information': "Any additional information you'd like us to know"
        }
