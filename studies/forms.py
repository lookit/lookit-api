import json

from ace_overlay.widgets import AceOverlayWidget
from bitfield.forms import BitFieldCheckboxSelectMultiple
from django import forms
from django.forms import ModelForm, Textarea

from studies.models import EligibleParticipantQueryModel, Response, Study


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


class BaseStudyForm(ModelForm):
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


STUDY_HELP_TEXT_INITIAL = """<p>After selecting a study type above, you'll be asked 
    to fill out some study type metadata as well. This metadata is unique to the 
    study type, and provides important configurations for building your study.</p>
    <p>If you're not sure what to enter here, just leave the defaults (you can change this later).</p>
    <p>For more information on study types and their metadata, please
    <a href="https://lookit.readthedocs.io/en/develop/experimenter.html#editing-study-type">see the documentation.</a></p>"""

STUDY_HELP_TEXT_EDIT = (
    STUDY_HELP_TEXT_INITIAL
    + """<p> Once you've filled in the 
    required metadata, you'll have to build the dependencies for your experiment in order 
    to deploy it, which you can do from the detail page. However, you'll probably want 
    to see what your experiment looks like before you actually deploy it and start 
    collecting data! You can do that by clicking the "Build Preview Dependencies" button and 
    then clicking on "See Preview" above after the build finishes.</p>"""
)


class StudyEditForm(BaseStudyForm):
    """Form for editing an existing a new study.

    Study type is NOT included in this form as that submission is handled separately during edit, although metadata
    about the field is stored here for consistency.
    """

    structure = forms.CharField(
        label="Build Study - Add JSON",
        widget=AceOverlayWidget(
            mode="json",
            wordwrap=True,
            theme="textmate",
            width="100%",
            height="100%",
            showprintmargin=False,
        ),
        required=False,
        help_text="Add the frames of your study as well as the sequence of those frames.  This can be added later.",
    )

    def clean_structure(self):
        structure = self.cleaned_data["structure"]
        try:
            json_data = json.loads(structure)  # loads string as json
        except:
            raise forms.ValidationError(
                "Save failed due to invalid JSON! Please use valid JSON and save again. If you reload this page, all changes will be lost."
            )
        return json_data

    class Meta:
        model = Study
        fields = [
            "name",
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
            "structure",
        ]
        labels = {
            "short_description": "Short Description",
            "long_description": "Purpose",
            "exit_url": "Exit URL",
            "criteria": "Participant Eligibility",
            "contact_info": "Researcher Contact Information",
            "public": "Discoverable - Do you want this study to be publicly discoverable on Lookit once activated?",
            "study_type": "Study Type",
            "compensation_description": "Compensation",
        }
        widgets = {
            "short_description": Textarea(attrs={"rows": 2}),
            "long_description": Textarea(attrs={"rows": 2}),
            "compensation_description": Textarea(attrs={"rows": 2}),
            "exit_url": Textarea(attrs={"rows": 1}),
            "criteria": Textarea(attrs={"rows": 1}),
            "duration": Textarea(attrs={"rows": 1}),
            "contact_info": Textarea(attrs={"rows": 1}),
        }

        help_texts = {
            "image": "Please keep your file size less than 1 MB",
            "exit_url": "Specify the page where you want to send your participants after they've completed the study.",
            "short_description": "Describe what happens during your study here. This should give families a concrete idea of what they will be doing - e.g., reading a story together and answering questions, watching a short video, playing a game about numbers.",
            "long_description": "Explain the purpose of your study here. This should address what question this study answers AND why that is an interesting or important question, in layperson-friendly terms.",
            "contact_info": "This should give the name of the PI for your study, and an email address where the PI or study staff can be reached with questions. Format: PIs Name (contact: youremail@lab.edu)",
            "criteria": "Text shown to families - this is not used to actually verify eligibility.",
            "study_type": STUDY_HELP_TEXT_EDIT,
            "compensation_description": "Provide a description of any compensation for participation, including when and how participants will receive it and any limitations or eligibility criteria (e.g., only one gift card per participant, being in age range for study, child being visible in consent video). Please see the Terms of Use for details on allowable compensation and restrictions. If this field is left blank it will not be displayed to participants.",
        }


# Form for creating a new study. Study type is included as part of this form.
class StudyForm(StudyEditForm):
    class Meta(StudyEditForm.Meta):
        help_texts = StudyEditForm.Meta.help_texts.copy()
        help_texts["study_type"] = STUDY_HELP_TEXT_INITIAL

        fields = StudyEditForm.Meta.fields + ["study_type"]


class StudyBuildForm(forms.ModelForm):
    structure = forms.CharField(
        label="Build Study - Add JSON",
        widget=AceOverlayWidget(
            mode="json",
            wordwrap=True,
            theme="textmate",
            width="100%",
            height="100%",
            showprintmargin=False,
        ),
        required=False,
        help_text="Add the frames of your study as well as the sequence of those frames.",
    )

    def clean_structure(self):
        structure = self.cleaned_data["structure"]
        try:
            json_data = json.loads(structure)  # loads string as json
        except:
            raise forms.ValidationError("Invalid JSON")
        return json_data

    class Meta:
        model = Study
        fields = ["structure"]


class EligibleParticipantQueryModelForm(ModelForm):
    """Modifying the stateful backing for the queryset for eligible participants."""

    # TODO: validation function
    # def clean(self):
    #     cleaned_data = super().clean()
    #     return

    class Meta:
        fields = (
            "include_conditions",
            "exclude_conditions",
            "include_languages",
            "exclude_languages",
            "age_range_start_years",
            "age_range_start_months",
            "age_range_start_days",
            "age_range_end_years",
            "age_range_end_months",
            "age_range_end_days",
            "gender_specification",
            "gestational_age_start",
            "gestational_age_end",
            "gestational_age_include_na",
        )
        model = EligibleParticipantQueryModel

        widgets = {
            "include_conditions": BitFieldCheckboxSelectMultiple(
                attrs={"class": "column-checkbox"}
            ),
            "exclude_conditions": BitFieldCheckboxSelectMultiple(
                attrs={"class": "column-checkbox"}
            ),
        }
