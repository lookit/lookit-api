import json

from ace_overlay.widgets import AceOverlayWidget
from django import forms
from django.db.models import Q
from django.forms import ModelForm, Textarea
from guardian.shortcuts import get_objects_for_user

from accounts.queries import compile_expression
from studies.models import Lab, Response, Study
from studies.permissions import LabPermission, StudyPermission

CRITERIA_EXPRESSION_HELP_LINK = "https://lookit.readthedocs.io/en/develop/researchers-set-study-fields.html#criteria-expression"
STUDY_TYPE_HELP_LINK = "https://lookit.readthedocs.io/en/develop/researchers-manage-studies.html#editing-study-type"
PROTOCOL_CONFIG_HELP_LINK = (
    "https://lookit.readthedocs.io/en/develop/researchers-create-experiment.html"
)
PROTOCOL_GENERATOR_HELP_LINK = (
    "https://lookit.readthedocs.io/en/develop/researchers-protocol-generators.html"
)
PROTOCOL_HELP_TEXT_EDIT = f"Configure frames to use in your study and specify their order. For information on how to set up your protocol, please <a href={PROTOCOL_CONFIG_HELP_LINK}>see the documentation.</a>"
PROTOCOL_HELP_TEXT_INITIAL = f"{PROTOCOL_HELP_TEXT_EDIT}  You can leave the default for now and come back to this later."
DEFAULT_GENERATOR = """function generateProtocol(child, pastSessions) {
    /*
     * Generate the protocol for this study.
     * 
     * @param {Object} child 
     *    The child currently participating in this study. Includes fields: 
     *      givenName (string)
     *      birthday (Date)
     *      gender (string, 'm' / 'f' / 'o')
     *      ageAtBirth (string, e.g. '25 weeks'. One of '40 or more weeks', 
     *          '39 weeks' through '24 weeks', 'Under 24 weeks', or 
     *          'Not sure or prefer not to answer')
     *      additionalInformation (string)
     *      languageList (string) space-separated list of languages child is 
     *          exposed to (2-letter codes)
     *      conditionList (string) space-separated list of conditions/characteristics
     *          of child from registration form, as used in criteria expression
     *          - e.g. "autism_spectrum_disorder deaf multiple_birth"
     * 
     *      Use child.get to access these fields: e.g., child.get('givenName') returns
     *      the child's given name.
     * 
     * @param {!Array<Object>} pastSessions
     *     List of past sessions for this child and this study, in reverse time order:
     *     pastSessions[0] is THIS session, pastSessions[1] the previous session, 
     *     back to pastSessions[pastSessions.length - 1] which has the very first 
     *     session.
     * 
     *     Each session has the following fields, corresponding to values available
     *     in Lookit:
     * 
     *     createdOn (Date)
     *     conditions
     *     expData
     *     sequence
     *     completed
     *     globalEventTimings
     *     completedConsentFrame (note - this list will include even "responses") 
     *          where the user did not complete the consent form!
     *     demographicSnapshot
     *     isPreview
     * 
     * @return {Object} Protocol specification for Lookit study; object with 'frames' 
     *    and 'sequence' keys.
     */
        var protocol = {
            frames: {},
            sequence: []
        };
        return protocol;
    } 
"""


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
            "slug",
            "description",
            "irb_contact_info",
        ]
        widgets = {
            "slug": forms.TextInput(attrs={"placeholder": "my-lab-name"}),
        }


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
            "slug",
            "description",
            "irb_contact_info",
            "approved_to_test",
        ]
        widgets = {
            "slug": forms.TextInput(attrs={"placeholder": "my-lab-name"}),
        }


class StudyForm(ModelForm):
    """Base form for creating or editing a study"""

    # Eventually when we support other experiment runner types (labjs, jspsych, etc.)
    # we may do one of the following:
    # - separate the 'study protocol specification' fields into their own
    # form which collects various information and cleans it and sets a single 'structure' object,
    # with the selected
    # - creating a model to represent each study type, likely such that each study has a nullable
    # relation for lookit_runner_protocol, jspsych_runner_protocol, etc.

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

    external = forms.BooleanField(
        required=False,
        help_text="Post an external link to a study, rather than Lookit's experiment builder.",
    )
    scheduled = forms.BooleanField(
        required=False,
        help_text="Schedule participants for one-on-one appointments with a researcher.",
    )

    # Define initial value here rather than providing actual default so that any updates don't
    # require migrations: this isn't a true "default" value that would ever be used, but rather
    # a helpful skeleton to guide the user
    generator = forms.CharField(
        label="Protocol generator",
        widget=AceOverlayWidget(
            mode="javascript",
            wordwrap=True,
            theme="textmate",
            width="100%",
            height="100%",
            showprintmargin=False,
        ),
        required=False,
        help_text=(
            "Write a Javascript function that returns a study protocol object with 'frames' and "
            "'sequence' keys. This allows more flexible randomization and dependence on past sessions in "
            f"complex cases. See <a href={PROTOCOL_GENERATOR_HELP_LINK}>documentation</a> for details."
        ),
        initial=DEFAULT_GENERATOR,
    )

    def clean(self):
        cleaned_data = super().clean()
        min_age_days = self.cleaned_data.get("min_age_days")
        min_age_months = self.cleaned_data.get("min_age_months")
        min_age_years = self.cleaned_data.get("min_age_years")
        max_age_days = self.cleaned_data.get("max_age_days")
        max_age_months = self.cleaned_data.get("max_age_months")
        max_age_years = self.cleaned_data.get("max_age_years")
        if (min_age_years * 365 + min_age_months * 30 + min_age_days) > (
            max_age_years * 365 + max_age_months * 30 + max_age_days
        ):
            raise forms.ValidationError(
                "The maximum age must be greater than the minimum age."
            )
        return cleaned_data

    def clean_structure(self):
        structure_text = self.cleaned_data["structure"]

        # Parse edited text representation of structure object, and additionally store the
        # exact text (so user can organize frames, parameters, etc. for readability)
        try:
            json_data = json.loads(structure_text)  # loads string as json
            json_data["exact_text"] = structure_text
        except:
            raise forms.ValidationError(
                "Saving protocol configuration failed due to invalid JSON! Please use valid JSON and save again. If you reload this page, all changes will be lost."
            )

        # Store the object which includes the exact text (not just the text)
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
            "preview_summary",
            "short_description",
            "purpose",
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
            "generator",
            "use_generator",
            "criteria_expression",
        ]
        labels = {
            "name": "Study Name",
            "image": "Study Image",
            "preview_summary": "Preview Summary",
            "short_description": "Short Description",
            "purpose": "Purpose",
            "exit_url": "Exit URL",
            "criteria": "Participant Eligibility Description",
            "contact_info": "Researcher Contact Information",
            "public": "Discoverable",
            "shared_preview": "Share Preview",
            "study_type": "Experiment Runner Type",
            "compensation_description": "Compensation",
            "use_generator": "Use protocol generator (advanced)",
        }
        widgets = {
            "preview_summary": Textarea(attrs={"rows": 2}),
            "short_description": Textarea(attrs={"rows": 2}),
            "purpose": Textarea(attrs={"rows": 2}),
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
            "image": "This is the image participants will see when browsing studies. Please keep your file size less than 1 MB.",
            "exit_url": "Specify the page where you want to send your participants after they've completed the study. (The 'Past studies' page on Lookit is a good default option.)",
            "preview_summary": "This is the text participants will see when browsing studies. Please keep your description under 100 words.",
            "short_description": "Describe what happens during your study here. This should give families a concrete idea of what they will be doing - e.g., reading a story together and answering questions, watching a short video, playing a game about numbers. If you are running a scheduled study, make sure to include a description of how they will sign up and access the study session.",
            "purpose": "Explain the purpose of your study here. This should address what question this study answers AND why that is an interesting or important question, in layperson-friendly terms.",
            "contact_info": "This should give the name of the PI for your study, and an email address where the PI or study staff can be reached with questions. Format: PIs Name (contact: youremail@lab.edu)",
            "criteria": "Text shown to families - this is not used to actually verify eligibility.",
            "compensation_description": "Provide a description of any compensation for participation, including when and how participants will receive it and any limitations or eligibility criteria (e.g., only one gift card per participant, being in age range for study, child being visible in consent video). Please see the Terms of Use for details on allowable compensation and restrictions. If this field is left blank it will not be displayed to participants.",
            "criteria_expression": (
                "Provide a relational expression indicating any criteria for eligibility besides the age range specified below."
                "For more information on how to structure criteria expressions, please visit our "
                f"<a href={CRITERIA_EXPRESSION_HELP_LINK}>documentation</a>."
            ),
            "public": "List this study on the 'Studies' page once you start it.",
            "shared_preview": "Allow other Lookit researchers to preview your study and give feedback.",
            "study_type": f"""<p>After selecting an experiment runner type above, you'll be asked
                to provide some additional configuration information.</p>
                <p>If you're not sure what to enter here, just leave the defaults (you can change this later).
                For more information on experiment runner types, please
                <a href={STUDY_TYPE_HELP_LINK}>see the documentation.</a></p>""",
            "structure": PROTOCOL_HELP_TEXT_INITIAL,
        }


class StudyEditForm(StudyForm):
    """Form for editing study"""

    def __init__(self, user=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["external"].disabled = True
        self.fields["structure"].help_text = PROTOCOL_HELP_TEXT_EDIT
        # Restrict ability to edit study lab based on user permissions
        can_change_lab = user.has_study_perms(
            StudyPermission.CHANGE_STUDY_LAB, self.instance
        )
        if can_change_lab:
            self.fields["lab"].help_text = (
                "Which lab this study will be affiliated with. Be careful changing the lab of an existing study: "
                "this will affect who can view and edit the study."
            )
            # Limit labs to change to: current lab, or labs this user is a member of & can create studies in
            self.fields["lab"].queryset = Lab.objects.filter(
                Q(
                    id__in=get_objects_for_user(
                        user,
                        LabPermission.CREATE_LAB_ASSOCIATED_STUDY.prefixed_codename,
                    ).only("id")
                )
                | (Q(uuid=self.instance.lab.uuid))
            )

        else:
            # Ensure we display the current lab on the edit form, even if user isn't part of this lab (which
            # isn't technically possible the way permissions are set up, but in principle options should be
            # current if lab can't be changed, and user's labs otherwise)
            self.fields["lab"].queryset = Lab.objects.filter(
                uuid=self.instance.lab.uuid
            )
            self.fields["lab"].disabled = True

    def clean_external(self):
        study = self.instance
        external = self.cleaned_data["external"]

        if (not external and study.study_type.is_external) or (
            external and study.study_type.is_ember_frame_player
        ):
            raise forms.ValidationError("Attempt to change study type not allowed.")

        return external


class StudyCreateForm(StudyForm):
    """Form for creating a new study"""

    def __init__(self, user=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Limit initial lab options to labs this user is a member of & can create studies in
        self.fields["lab"].queryset = Lab.objects.filter(
            id__in=get_objects_for_user(
                user, LabPermission.CREATE_LAB_ASSOCIATED_STUDY.prefixed_codename
            ).only("id")
        )
