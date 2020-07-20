import datetime

from bitfield.forms import BitFieldCheckboxSelectMultiple
from django import forms
from django.contrib.auth.forms import PasswordChangeForm, UserCreationForm
from django.core.exceptions import ValidationError

from accounts.models import Child, DemographicData, User

from django.utils.translation import gettext_lazy as _

class UserForm(forms.ModelForm):
    class Meta:
        model = User
        exclude = ("password",)


class ParticipantSignupForm(UserCreationForm):
    nickname = forms.CharField(required=True, max_length=255)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["password1"].widget.attrs["autocomplete"] = "new-password"
        self.fields["password2"].widget.attrs["autocomplete"] = "new-password"

    def save(self, commit=True):
        user = super(UserCreationForm, self).save(commit=False)
        user.set_password(self.cleaned_data["password1"])
        user.is_active = True
        if commit:
            user.save()
        return user

    class Meta:
        model = User
        fields = ("username", "nickname")
        exclude = (
            "user_permissions",
            "groups",
            "_identicon",
            "labs",
            "is_active",
            "is_staff",
            "is_superuser",
            "last_login",
            "middle_name",
            "last_name",
        )


class ParticipantUpdateForm(forms.ModelForm):
    nickname = forms.CharField(required=True, max_length=255)

    def __init__(self, *args, **kwargs):
        if "user" in kwargs:
            kwargs.pop("user")
        super().__init__(*args, **kwargs)
        instance = getattr(self, "instance", None)
        self.fields["username"].widget.attrs.pop("autofocus", None)

    class Meta:
        model = User
        fields = ("username", "nickname")
        labels = {"username": "Email address"}


class ParticipantPasswordForm(PasswordChangeForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["old_password"].widget.attrs.pop("autofocus", None)
        self.fields["new_password1"].widget.attrs["autocomplete"] = "new-password"
        self.fields["new_password2"].widget.attrs["autocomplete"] = "new-password"

    class Meta:
        model = User


class EmailPreferencesForm(forms.ModelForm):
    class Meta:
        model = User
        fields = (
            "email_next_session",
            "email_new_studies",
            "email_study_updates",
            "email_response_questions",
        )
        labels = {
            "email_next_session": "It's time for another session of a study we are currently participating in",
            "email_new_studies": "A new study is available for one of my children",
            "email_study_updates": "There's an update about a study we participated in (for example, results are published)",
            "email_response_questions": "A researcher has questions about my individual responses (for example, if I report a technical problem during the study)",
        }


class DemographicDataForm(forms.ModelForm):
    race_identification = forms.MultipleChoiceField(
        choices=DemographicData.RACE_CHOICES,
        widget=forms.CheckboxSelectMultiple(),
        label="What category(ies) does your family identify as?",
        required=False,
    )

    class Meta:
        model = DemographicData
        exclude = ("created_at", "previous", "user", "extra", "uuid")
        fields = (
            "country",
            "state",
            "density",
            "languages_spoken_at_home",
            "number_of_children",
            "child_birthdays",
            "number_of_guardians",
            "number_of_guardians_explanation",
            "race_identification",
            "age",
            "gender",
            "education_level",
            "spouse_education_level",
            "annual_income",
            "number_of_books",
            "lookit_referrer",
            "additional_comments",
        )

        help_texts = {
            "child_birthdays": "Enter as a comma-separated list: YYYY-MM-DD, YYYY-MM-DD, ...",
            "number_of_books": "Numerical answers only - a rough guess is fine!",
        }

        labels = {
            "country": _("What country do you live in?"),
            "state": _("What state do you live in?"),
            "density": _("How would you describe the area where you live?"),
            "languages_spoken_at_home": _( "What language(s) does your family speak at home?"),
            "number_of_children": _("How many children do you have?"),
            "child_birthdays": _("For each child, please enter his or her birthdate:"),
            "number_of_guardians": _("How many parents/guardians do your children live with?"),
            "race_identification": _("What category(ies) does your family identify as?"),
            "age": _("What is your age?"),
            "gender": _("What is your gender?"),
            "education_level": _("What is the highest level of education you've completed?"),
            "spouse_education_level": _("What is the highest level of education your spouse has completed?"),
            "annual_income": _("What is your approximate family yearly income (in US dollars)?"),
            "number_of_books": _("About how many children's books are there in your home?"),
            "additional_comments": _("Anything else you'd like us to know?"),
            "lookit_referrer": _("How did you hear about Lookit?"),
            "number_of_guardians_explanation": _("If the answer varies due to shared custody arrangements or travel, please enter the number of parents/guardians your children are usually living with or explain."),
        }

        widgets = {
            "languages_spoken_at_home": forms.Textarea(attrs={"rows": 1}),
            "additional_comments": forms.Textarea(attrs={"rows": 2}),
            "number_of_guardians_explanation": forms.Textarea(attrs={"rows": 2}),
            "lookit_referrer": forms.Textarea(attrs={"rows": 2}),
        }


class ChildForm(forms.ModelForm):
    birthday = forms.DateField(
        widget=forms.DateInput(attrs={"class": "datepicker"}),
        help_text="This lets us figure out exactly how old your child is when they participate in a study. We never publish children's birthdates or information that would allow a reader to calculate the birthdate.",
    )

    def clean_birthday(self):
        date = self.cleaned_data["birthday"]
        if date > datetime.date.today():
            raise ValidationError("Birthdays cannot be in the future.")
        return date

    class Meta:
        model = Child
        fields = (
            "given_name",
            "birthday",
            "gender",
            "gestational_age_at_birth",
            "existing_conditions",
            "languages_spoken",
            "additional_information",
        )

        labels = {
            "given_name": "First Name",
            "birthday": "Birthday",
            "gestational_age_at_birth": "Gestational Age at Birth",
            "additional_information": "Any additional information you'd like us to know",
            "existing_conditions": "Characteristics and conditions",
            "languages_spoken": "Languages this child is exposed to at home, school, or with another caregiver.",
        }

        help_texts = {
            "given_name": "This lets you select the correct child to participate in a particular study. A nickname or initials are fine! We may include your child's name in email to you (for instance, \"There's a new study available for Molly!\") but will never publish names or use them in our research.",
            "additional_information": "For instance, diagnosed developmental disorders or vision or hearing problems",
            "gestational_age_at_birth": "Please round down to the nearest full week of pregnancy completed",
        }

        widgets = {
            "existing_conditions": BitFieldCheckboxSelectMultiple(
                attrs={"class": "column-checkbox"}
            ),
            "languages_spoken": BitFieldCheckboxSelectMultiple(
                attrs={"class": "column-checkbox"}
            ),
        }


class ChildUpdateForm(forms.ModelForm):
    birthday = forms.DateField(disabled=True, help_text="YYYY-MM-DD")

    class Meta:
        model = Child
        fields = (
            "given_name",
            "birthday",
            "gender",
            "gestational_age_at_birth",
            "existing_conditions",
            "languages_spoken",
            "additional_information",
        )

        labels = {
            "given_name": "First Name",
            "birthday": "Birthday",
            "gestational_age_at_birth": "Gestational Age at Birth",
            "additional_information": "Any additional information you'd like us to know",
            "existing_conditions": "Characteristics and conditions",
            "languages_spoken": "Languages this child is exposed to at home, school, or with another caregiver.",
        }

        help_texts = {
            "given_name": "This lets you select the correct child to participate in a particular study. A nickname or initials are fine! We may include your child's name in email to you (for instance, \"There's a new study available for Molly!\") but will never publish names or use them in our research.",
            "additional_information": "For instance, diagnosed developmental disorders or vision or hearing problems",
        }

        widgets = {
            "existing_conditions": BitFieldCheckboxSelectMultiple(
                attrs={"class": "column-checkbox"}
            ),
            "languages_spoken": BitFieldCheckboxSelectMultiple(
                attrs={"class": "column-checkbox"}
            ),
        }
