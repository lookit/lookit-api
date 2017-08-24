from django import forms
from django.contrib.auth.forms import UserCreationForm, PasswordChangeForm, UserChangeForm
from django.forms.widgets import DateInput

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
    nickname = forms.CharField(required=True, max_length=255)

    def save(self, commit=True):
        user = super(UserCreationForm, self).save(commit=False)
        user.set_password(self.cleaned_data["password1"])
        user.is_active = True
        if commit:
            user.save()
        return user

    class Meta:
        model = User
        fields = ('username', 'nickname')
        exclude = ('user_permissions', 'groups', '_identicon', 'organization',
                   'is_active', 'is_staff', 'is_superuser', 'last_login',
                   'middle_name', 'last_name')


class ParticipantUpdateForm(forms.ModelForm):
    nickname = forms.CharField(required=True, max_length=255)

    def __init__(self, *args, **kwargs):
        if 'user' in kwargs:
            kwargs.pop('user')
        super().__init__(*args, **kwargs)
        instance = getattr(self, 'instance', None)
        self.fields['username'].widget.attrs['autofocus'] = 'autofocus'

    class Meta:
        model = User
        fields = ('username', 'nickname')
        labels = {
            'username': 'Email address'
        }


class ParticipantPasswordForm(PasswordChangeForm):
    class Meta:
        model = User


class EmailPreferencesForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ('email_next_session', 'email_new_studies', 'email_study_updates', 'email_response_questions')
        labels = {
            'email_next_session': "It's time for another session of a study we are currently participating in",
            'email_new_studies': "A new study is available for one of my children",
            'email_study_updates': "There's an update about a study we participated in (for example, results are published)",
            'email_response_questions': "A researcher has questions about my individual responses (for example, if I report a technical problem during the study)"
        }


class DemographicDataForm(forms.ModelForm):
    race_identification = forms.MultipleChoiceField(
        choices = DemographicData.RACE_CHOICES,
        widget=forms.CheckboxSelectMultiple(),
        label="What category(ies) does your family identify as?",
        required=False
    )
    class Meta:
        model = DemographicData
        exclude = ('created_at', 'previous', 'user', 'extra', 'uuid' )
        fields = ('country', 'state', 'density', 'languages_spoken_at_home', 'number_of_children', 'child_birthdays', 'number_of_guardians',
        'number_of_guardians_explanation', 'race_identification', 'age', 'gender', 'education_level', 'spouse_education_level', 'annual_income',
        'number_of_books', 'lookit_referrer', 'additional_comments')

        help_texts = {
            'child_birthdays': 'Enter as a comma-separated list: YYYY-MM-DD, YYYY-MM-DD, ...'
        }

        labels = {
            'country': 'What country do you live in?',
            'state': 'What state do you live in?',
            'density': 'How would you describe the area where you live?',
            'languages_spoken_at_home': 'What language(s) does your family speak at home?',
            'number_of_children': 'How many children do you have?',
            'child_birthdays': 'For each child, please enter his or her birthdate:',
            'number_of_guardians': 'How many parents/guardians do your children live with?',
            'race_identification': 'What category(ies) does your family identify as?',
            'age': "What is your age?",
            'gender': "What is your gender?",
            'education_level': "What is the highest level of education you've completed?",
            'spouse_education_level': 'What is the highest level of education your spouse has completed?',
            'annual_income': 'What is your approximate family yearly income (in US dollars)?',
            'number_of_books': "About how many children's books are there in your home?",
            'additional_comments': "Anything else you'd like us to know?",
            'lookit_referrer': 'How did you hear about Lookit?',
            'number_of_guardians_explanation': 'If the answer varies due to shared custody arrangements or travel, please enter the number of parents/guardians your children are usually living with or explain.',
        }

        widgets = {
            'languages_spoken_at_home': forms.Textarea(attrs={'rows': 1}),
            'additional_comments': forms.Textarea(attrs={'rows':2}),
            'number_of_guardians_explanation': forms.Textarea(attrs={'rows':2}),
            'lookit_referrer': forms.Textarea(attrs={'rows':2})
        }


class ChildForm(forms.ModelForm):
    birthday = forms.DateField(widget=forms.DateInput(attrs={'class': 'datepicker'}), help_text="This lets us figure out exactly how old your child is when they participate in a study. We never publish children\'s birthdates or information that would allow a reader to calculate the birthdate.")
    class Meta:
        model = Child
        fields = ('given_name', 'birthday', 'gender', 'age_at_birth', 'additional_information')

        labels = {
            'given_name': 'First Name',
            'birthday': "Birthday",
            'age_at_birth': 'Gestational Age at Birth',
            'additional_information': "Any additional information you'd like us to know"
        }

        help_texts = {
            'given_name': 'This lets you select the correct child to participate in a particular study. A nickname or initials are fine! We may include your child\'s name in email to you (for instance, "There\'s a new study available for Molly!") but will never publish names or use them in our research.',
            'additional_information': "for instance, diagnosed developmental disorders or vision or hearing problems"
        }


class ChildUpdateForm(forms.ModelForm):
    birthday = forms.DateField(disabled=True, help_text='YYYY-MM-DD')

    class Meta:
        model = Child
        fields = ('given_name', 'birthday', 'gender', 'age_at_birth', 'additional_information')

        labels = {
            'given_name': 'First Name',
            'birthday': "Birthday",
            'age_at_birth': 'Gestational Age at Birth',
            'additional_information': "Any additional information you'd like us to know"
        }

        help_texts = {
            'given_name': 'This lets you select the correct child to participate in a particular study. A nickname or initials are fine! We may include your child\'s name in email to you (for instance, "There\'s a new study available for Molly!") but will never publish names or use them in our research.',
            'additional_information': "for instance, diagnosed developmental disorders or vision or hearing problems",
        }
