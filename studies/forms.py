import json

from ace_overlay.widgets import AceOverlayWidget
from django import forms
from django.forms import ModelForm, Textarea

from accounts.queries import compile_expression
from studies.models import Lab, Response, Study
from studies.permissions import StudyPermission

CRITERIA_EXPRESSION_HELP_LINK = "https://lookit.readthedocs.io/en/develop/researchers-set-study-fields.html#criteria-expression"
STUDY_TYPE_HELP_LINK = "https://lookit.readthedocs.io/en/develop/researchers-manage-studies.html#editing-study-type"
PROTOCOL_CONFIG_HELP_LINK = (
    "https://lookit.readthedocs.io/en/develop/researchers-create-experiment.html"
)


class ResponseForm(ModelForm):
    results = forms.CharField(
        widget=AceOverlayWidget(
            mode="json",
            wordwrap=True,
            theme="textmate",
            width="100%",
            height="100%",
            showprintmargin=False,
        ),
        required=False,
    )

    class Meta:
        fields = ("study", "child", "demographic_snapshot", "results")
        model = Response


STUDY_TYPE_HELP_TEXT_INITIAL = f"""<p>After selecting an experiment runner type above, you'll be asked
    to provide some additional configuration information.</p>
    <p>If you're not sure what to enter here, just leave the defaults (you can change this later).
    For more information on experiment runner types, please
    <a href={STUDY_TYPE_HELP_LINK}>see the documentation.</a></p>"""

# Leave the same for now but may change in the future
STUDY_TYPE_HELP_TEXT_EDIT = STUDY_TYPE_HELP_TEXT_INITIAL

PROTOCOL_HELP_TEXT_EDIT = f"Configure frames to use in your study and specify their order. For information on how to set up your protocol, please <a href={PROTOCOL_CONFIG_HELP_LINK}>see the documentation.</a>"

PROTOCOL_HELP_TEXT_INITIAL = f"{PROTOCOL_HELP_TEXT_EDIT}  You can leave the default for now and come back to this later."


class LabForm(ModelForm):
    class Meta:
        model = Lab
        fields = [
            "name",
            "institution",
            "principal_investigator_name",
            "contact_email",
            "contact_phone",
            "lab_website",
            "description",
            "irb_contact_info",
        ]


class LabApprovalForm(ModelForm):
    class Meta:
        model = Lab
        fields = [
            "name",
            "institution",
            "principal_investigator_name",
            "contact_email",
            "contact_phone",
            "lab_website",
            "description",
            "irb_contact_info",
            "approved_to_test",
        ]


class StudyForm(ModelForm):
    """Base form for creating or editing a study"""

    structure = forms.CharField(
        label="Protocol configuration",
        widget=AceOverlayWidget(
            mode="json",
            wordwrap=True,
            theme="textmate",
            width="100%",
            height="100%",
            showprintmargin=False,
        ),
        required=False,
    )

    def __init__(self, *args, **kwargs):
        # Limit lab options to labs this user is a member of
        user = kwargs.pop("user")
        super().__init__(*args, **kwargs)
        self.fields["lab"].queryset = user.labs.all()

    def clean(self):
        cleaned_data = super().clean()
        min_age_days = self.cleaned_data.get("min_age_days")
        min_age_months = self.cleaned_data.get("min_age_months")
        min_age_years = self.cleaned_data.get("min_age_years")
        max_age_days = self.cleaned_data.get("max_age_days")
        max_age_months = self.cleaned_data.get("max_age_months")
        max_age_years = self.cleaned_data.get("max_age_years")
        if (min_age_years + min_age_months / 12 + min_age_days / 365) > (
            max_age_years + max_age_months / 12 + max_age_days / 365
        ):
            raise forms.ValidationError(
                "The maximum age must be greater than the minimum age."
            )
        return cleaned_data

    def clean_structure(self):
        structure = self.cleaned_data["structure"]

        try:
            json_data = json.loads(structure)  # loads string as json
        except:
            raise forms.ValidationError(
                "Saving protocol configuration failed due to invalid JSON! Please use valid JSON and save again. If you reload this page, all changes will be lost."
            )

        return json_data

    def clean_criteria_expression(self):
        criteria_expression = self.cleaned_data["criteria_expression"]
        try:
            compile_expression(criteria_expression)
        except Exception as e:
            raise forms.ValidationError(f"Invalid criteria expression:\n{e.args[0]}")

        return criteria_expression

    class Meta:
        model = Study
        fields = [
            "name",
            "lab",
            "image",
            "short_description",
            "long_description",
            "compensation_description",
            "exit_url",
            "criteria",
            "min_age_days",
            "min_age_months",
            "min_age_years",
            "max_age_days",
            "max_age_months",
            "max_age_years",
            "duration",
            "contact_info",
            "public",
            "shared_preview",
            "structure",
            "criteria_expression",
            "study_type",
        ]
        labels = {
            "short_description": "Short Description",
            "long_description": "Purpose",
            "exit_url": "Exit URL",
            "criteria": "Participant Eligibility Description",
            "contact_info": "Researcher Contact Information",
            "public": "Discoverable - List this study on the 'Studies' page once you start it?",
            "shared_preview": "Share preview - Allow other Lookit researchers to preview your study and give feedback?",
            "study_type": "Experiment Runner Type",
            "compensation_description": "Compensation",
        }
        widgets = {
            "short_description": Textarea(attrs={"rows": 2}),
            "long_description": Textarea(attrs={"rows": 2}),
            "compensation_description": Textarea(attrs={"rows": 2}),
            "exit_url": Textarea(attrs={"rows": 1}),
            "criteria": Textarea(
                attrs={"rows": 1, "placeholder": "For 4-year-olds who love dinosaurs"}
            ),
            "duration": Textarea(attrs={"rows": 1, "placeholder": "15 minutes"}),
            "contact_info": Textarea(
                attrs={
                    "rows": 1,
                    "placeholder": "Jane Smith (contact: jsmith@science.edu)",
                }
            ),
            "criteria_expression": Textarea(
                attrs={
                    "rows": 3,
                    "placeholder": (
                        "ex: ((deaf OR hearing_impairment) OR NOT speaks_en) "
                        "AND "
                        "(age_in_days >= 365 AND age_in_days <= 1095)"
                    ),
                }
            ),
        }

        help_texts = {
            "lab": "Which lab this study will be affiliated with",
            "image": "Please keep your file size less than 1 MB",
            "exit_url": "Specify the page where you want to send your participants after they've completed the study. (The 'Past studies' page on Lookit is a good default option.)",
            "short_description": "Describe what happens during your study here. This should give families a concrete idea of what they will be doing - e.g., reading a story together and answering questions, watching a short video, playing a game about numbers.",
            "long_description": "Explain the purpose of your study here. This should address what question this study answers AND why that is an interesting or important question, in layperson-friendly terms.",
            "contact_info": "This should give the name of the PI for your study, and an email address where the PI or study staff can be reached with questions. Format: PIs Name (contact: youremail@lab.edu)",
            "criteria": "Text shown to families - this is not used to actually verify eligibility.",
            "compensation_description": "Provide a description of any compensation for participation, including when and how participants will receive it and any limitations or eligibility criteria (e.g., only one gift card per participant, being in age range for study, child being visible in consent video). Please see the Terms of Use for details on allowable compensation and restrictions. If this field is left blank it will not be displayed to participants.",
            "criteria_expression": (
                "Provide a relational expression indicating any criteria for eligibility besides the age range specified below."
                "For more information on how to structure criteria expressions, please visit our "
                f"<a href={CRITERIA_EXPRESSION_HELP_LINK}>documentation</a>."
            ),
        }


class StudyEditForm(StudyForm):
    """Form for editing study"""

    def __init__(self, *args, **kwargs):
        user = kwargs.get("user")
        super().__init__(*args, **kwargs)
        self.fields["structure"].help_text = PROTOCOL_HELP_TEXT_EDIT
        self.fields["study_type"].help_text = STUDY_TYPE_HELP_TEXT_EDIT
        # Restrict ability to edit study lab based on user permissions
        can_change_lab = user.has_study_perms(
            StudyPermission.CHANGE_STUDY_LAB, self.instance
        )
        if can_change_lab:
            self.fields["lab"].help_text = (
                "Which lab this study will be affiliated with. Be careful changing the lab of an existing study: "
                "this will affect who can view and edit the study."
            )
        else:
            # Ensure we display the current lab on the edit form, even if user isn't part of this lab (which
            # isn't technically possible the way permissions are set up, but in principle options should be
            # current if lab can't be changed, and user's labs otherwise)
            self.fields["lab"].queryset = Lab.objects.filter(
                uuid=self.instance.lab.uuid
            )
            self.fields["lab"].disabled = True


class StudyCreateForm(StudyForm):
    """Form for creating a new study"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["structure"].help_text = PROTOCOL_HELP_TEXT_INITIAL
        self.fields["study_type"].help_text = STUDY_TYPE_HELP_TEXT_INITIAL
