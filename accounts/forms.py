import datetime
from enum import Enum

from bitfield.forms import BitFieldCheckboxSelectMultiple
from django import forms
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.forms import PasswordChangeForm as DjangoPasswordChangeForm
from django.contrib.auth.forms import UserCreationForm
from django.core.exceptions import ValidationError
from django.forms import EmailField
from django.utils.translation import gettext_lazy as _

from accounts.backends import two_factor_auth_backend
from accounts.models import Child, DemographicData, User


class ForceLowercaseEmailField(EmailField):
    def to_python(self, value):
        return super().to_python(value).lower()


class LowercaseUsernameUserCreationForm(UserCreationForm):
    def clean(self):
        """Check DB for case-insensitive matches on username.

        TODO: Consider using a migration to render this code obsolete.
        """
        cleaned_data = super().clean()
        username = cleaned_data.get("username")
        user_model_class = type(self.instance)

        try:
            user_model_class.objects.get_by_natural_key(username)
            raise ValidationError("A user with this username already exists!")
        except user_model_class.DoesNotExist:
            pass

        return cleaned_data

    class Meta(UserCreationForm.Meta):
        field_classes = {"username": ForceLowercaseEmailField}


class UserForm(forms.ModelForm):
    class Meta:
        model = User
        exclude = ("password",)


class TOTPField(forms.CharField):
    max_length = 6
    min_length = 6
    default_error_messages = {
        "invalid": _(
            "Enter a valid 6-digit one-time password from Google Authenticator"
        ),
    }

    def __init__(self, *args, **kwargs):
        super().__init__(
            max_length=self.max_length, min_length=self.min_length, *args, **kwargs
        )

    def widget_attrs(self, widget):
        """Override - used to update widget attrs in Field initializer."""
        attrs = super().widget_attrs(widget)
        return {**attrs, "placeholder": "123456", "style": "width: 50%;"}


class TOTPCheckForm(forms.Form):
    """Checks OTP codes.

    Should only appear in LoginView-derived classes, where the `request` object
    is set in view kwargs.
    """

    otp_code = TOTPField(label="Enter your one-time password (OTP code).")

    def __init__(self, *args, **kwargs):
        request = kwargs.pop("request")
        self.request = request
        self.otp = getattr(request.user, "otp")
        super().__init__(*args, **kwargs)

    def get_user(self):
        """User is already technically logged in."""
        return self.request.user

    def clean_otp_code(self):
        """Validation check on OTP code."""
        otp_code = self.cleaned_data["otp_code"]
        if self.otp.verify(otp_code):
            return otp_code
        else:
            raise forms.ValidationError(
                "Invalid OTP Code. Make sure that you type the 6 digit number "
                "exactly, and that you do so quickly (within the 30 second window)!"
            )


class TOTPLoginForm(AuthenticationForm):
    """Only used for Administrator Login, where 2FA is always required."""

    error_messages = {
        "invalid_login": _(
            "Please enter a correct %(username)s and password. Note that email "
            "and password fields may be case-sensitive. "
            "If you have turned on two-factor authentication, you will need "
            "a one-time password (OTP code) from Google Authenticator as well. "
        ),
        "inactive": _("This account is inactive."),
    }

    auth_code = TOTPField(
        label="Two Factor Auth Code", help_text="6 digit one-time code"
    )

    def clean(self):
        """Hook that gets run after all the fields are cleaned.

        Note: we are technically breaking LSP here since this is changing the
            functionality of the superclass rather than extending it, but
            AuthenticationForm is so dang close to what we want that it's ok
            to bend the rules a little bit.
        """
        username = self.cleaned_data.get("username")
        password = self.cleaned_data.get("password")

        # Auth code is "Optional" in the sense that TwoFactorAuthenticationBackend
        # will just flip a `using_2FA` flag as a signal to later requests - without
        # this flag, Researchers will be blocked from researcher views.
        auth_code = self.cleaned_data.get("auth_code")

        if username is not None and password:
            # Don't need ObjectPermissionBackend - just cut to the chase.
            self.user_cache = two_factor_auth_backend.authenticate(
                self.request, username=username, password=password, auth_code=auth_code
            )

            if self.user_cache is None:
                raise self.get_invalid_login_error()
            else:
                # Set the backend path as django.contrib.auth.authenticate would usually,
                # django.contrib.auth.login needs to know. This MUST also match the
                # class name listed in settings.AUTHENTICATION_BACKENDS in order for
                # AuthenticationMiddleware's request processor to work correctly, see:
                # https://github.com/django/django/blob/master/django/contrib/auth/__init__.py#L179
                self.user_cache.backend = (
                    "accounts.backends.TwoFactorAuthenticationBackend"
                )
                self.confirm_login_allowed(self.user_cache)

        return self.cleaned_data


class ResearcherRegistrationForm(LowercaseUsernameUserCreationForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Don't autofill passwords, in the interest of security.
        self.fields["password1"].widget.attrs["autocomplete"] = "new-password"
        self.fields["password2"].widget.attrs["autocomplete"] = "new-password"
        self.fields["given_name"].required = True
        self.fields["family_name"].required = True

    def save(self, commit=True):
        """Just flip the active and researcher flags."""
        user = super().save(commit=False)
        user.is_active = True
        user.is_researcher = True
        if commit:
            user.save()
        return user

    class Meta(LowercaseUsernameUserCreationForm.Meta):
        model = User
        fields = ("username", "nickname", "given_name", "family_name")
        labels = {
            "username": "Email address",
            "given_name": "Given Name",
            "family_name": "Family Name",
        }


class ParticipantSignupForm(LowercaseUsernameUserCreationForm):
    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data["password1"])
        # TODO: `active` default shouldn't be False - we'll need a migration
        #   to have True instead, and then we can drop this custom `save` method.
        user.is_active = True
        if commit:
            user.save()
        return user

    class Meta(LowercaseUsernameUserCreationForm.Meta):
        model = User
        fields = ("username", "nickname")
        labels = {
            "username": _("Email address"),
            "nickname": _("Nickname"),
        }


class AccountUpdateForm(forms.ModelForm):
    nickname = forms.CharField(required=True, max_length=255)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].widget.attrs.pop("autofocus", None)

    class Meta:
        model = User
        field_classes = {"username": ForceLowercaseEmailField}
        fields = ("username", "nickname")
        labels = {"username": _("Email address")}


class PasswordChangeForm(DjangoPasswordChangeForm):
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
            "email_next_session": _(
                "It's time for another session of a study we are currently participating in"
            ),
            "email_new_studies": _("A new study is available for one of my children"),
            "email_study_updates": _(
                "There's an update about a study we participated in (for example, results are published)"
            ),
            "email_response_questions": _(
                "A researcher has questions about my individual responses (for example, if I report a technical problem during the study)"
            ),
        }


class DemographicDataForm(forms.ModelForm):
    race_identification = forms.MultipleChoiceField(
        choices=DemographicData.RACE_CHOICES,
        widget=forms.CheckboxSelectMultiple(),
        label=_("What category(ies) does your family identify as?"),
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
            "education_level_free",
            "spouse_education_level",
            "annual_income",
            "number_of_books",
            "lookit_referrer",
            "additional_comments",
        )

        help_texts = {
            "child_birthdays": _(
                "Enter as a comma-separated list: YYYY-MM-DD, YYYY-MM-DD, ..."
            ),
            "number_of_books": _("Numerical answers only - a rough guess is fine!"),
        }

        labels = {
            "country": _("What country do you live in?"),
            "state": _("What state do you live in?"),
            "density": _("How would you describe the area where you live?"),
            "languages_spoken_at_home": _(
                "What language(s) does your family speak at home?"
            ),
            "number_of_children": _("How many children do you have?"),
            "child_birthdays": _("For each child, please enter his or her birthdate:"),
            "number_of_guardians": _(
                "How many parents/guardians do your children live with?"
            ),
            "race_identification": _(
                "What category(ies) does your family identify as?"
            ),
            "age": _("What is your age?"),
            "gender": _("What is your gender?"),
            "education_level": _(
                "What is the highest level of education you've completed?"
            ),
            "education_level_free": _(
                "What is the highest level of education you've completed (e.g., elementary school, vocational training, 3-year university degree, PhD)?"
            ),
            "spouse_education_level": _(
                "What is the highest level of education your spouse has completed?"
            ),
            "annual_income": _(
                "What is your approximate family yearly income (in US dollars)?"
            ),
            "number_of_books": _(
                "About how many children's books are there in your home?"
            ),
            "additional_comments": _("Anything else you'd like us to know?"),
            "lookit_referrer": _("How did you hear about Lookit?"),
            "number_of_guardians_explanation": _(
                "If the answer varies due to shared custody arrangements or travel, please enter the number of parents/guardians your children are usually living with or explain."
            ),
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
        help_text=_(
            "This lets us figure out exactly how old your child is when they participate in a study. We never publish children's birthdates or information that would allow a reader to calculate the birthdate."
        ),
    )

    def clean_birthday(self):
        date = self.cleaned_data["birthday"]
        if date > datetime.date.today():
            raise ValidationError(_("Birthdays cannot be in the future."))
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
            "given_name": _("First Name"),
            "birthday": _("Birthday"),
            "gender": _("Gender"),
            "gestational_age_at_birth": _("Gestational Age at Birth"),
            "additional_information": _(
                "Any additional information you'd like us to know"
            ),
            "existing_conditions": _("Characteristics and conditions"),
            "languages_spoken": _(
                "Languages this child is exposed to at home, school, or with another caregiver."
            ),
        }

        help_texts = {
            "given_name": _(
                "This lets you select the correct child to participate in a particular study. A nickname or initials are fine! We may include your child's name in email to you (for instance, \"There's a new study available for Molly!\") but will never publish names or use them in our research."
            ),
            "additional_information": _(
                "For instance, diagnosed developmental disorders or vision or hearing problems"
            ),
            "gestational_age_at_birth": _(
                "Please round down to the nearest full week of pregnancy completed"
            ),
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
            "given_name": _("First Name"),
            "birthday": _("Birthday"),
            "gender": _("Gender"),
            "gestational_age_at_birth": _("Gestational Age at Birth"),
            "additional_information": _(
                "Any additional information you'd like us to know"
            ),
            "existing_conditions": _("Characteristics and conditions"),
            "languages_spoken": _(
                "Languages this child is exposed to at home, school, or with another caregiver."
            ),
        }

        help_texts = {
            "given_name": _(
                "This lets you select the correct child to participate in a particular study. A nickname or initials are fine! We may include your child's name in email to you (for instance, \"There's a new study available for Molly!\") but will never publish names or use them in our research."
            ),
            "additional_information": _(
                "For instance, diagnosed developmental disorders or vision or hearing problems"
            ),
        }

        widgets = {
            "existing_conditions": BitFieldCheckboxSelectMultiple(
                attrs={"class": "column-checkbox"}
            ),
            "languages_spoken": BitFieldCheckboxSelectMultiple(
                attrs={"class": "column-checkbox"}
            ),
        }


class FormChoiceEnum(Enum):
    @classmethod
    def choices(cls):
        return [c.value for c in cls]


class StudyListSearchForm(forms.Form):
    class Tabs(FormChoiceEnum):
        all_studies = ("0", _("All studies"))
        synchronous_studies = ("1", _("Studies happening right now"))
        asynchronous_studies = ("2", _("Scheduled studies"))

    class Children(FormChoiceEnum):
        empty = ("", _("Find studies for..."))
        babies = ("0,1", _("babies (under 1)"))
        toddlers = ("1,3", _("toddlers (1-2)"))
        preschoolers = ("3,5", _("preschoolers (3-4)"))
        school_age_kids = ("5,18", _("school-age kids (5-17)"))
        adults = ("18,999", _("adults (18+)"))

    class StudyLocation(FormChoiceEnum):
        empty = ("0", _("Show studies that are..."))
        lookit = ("1", _("...happening on Lookit"))
        external = ("2", _("...happening on other websites"))

    child = forms.ChoiceField(choices=Children.choices(), required=False)
    search = forms.CharField(required=False)
    hide_studies_we_have_done = forms.BooleanField(
        label=_("Hide Studies We've Done"), required=False
    )
    study_list_tabs = forms.ChoiceField(
        choices=Tabs.choices(),
        initial=0,
        widget=forms.RadioSelect(attrs={"class": "hidden"}),
        required=False,
    )
    study_location = forms.ChoiceField(choices=StudyLocation.choices(), required=False)

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)

        children = None
        if self.user and self.user.is_authenticated:
            children = self.user.children.filter(deleted=False)

        if children and children.count():
            self.fields["child"].choices = [self.Children.empty.value] + [
                (c.pk, c.given_name) for c in children
            ]
        else:
            self.fields["hide_studies_we_have_done"].widget = forms.HiddenInput()

    def clean(self):
        cleaned_data = super().clean()
        child = cleaned_data["child"]
        if (
            not child
            or "," in child
            or (self.user.is_authenticated and child.isnumeric())
        ):
            return cleaned_data
        else:
            raise ValidationError("Child data doesn't match user authentication state.")


class PastStudiesFormTabChoices(Enum):
    lookit_studies = ("0", _("Lookit studies"))
    external_studies = ("1", _("External studies"))


class PastStudiesForm(forms.Form):
    past_studies_tabs = forms.ChoiceField(
        choices=[tc.value for tc in PastStudiesFormTabChoices],
        initial=0,
        widget=forms.RadioSelect,
        required=False,
    )
