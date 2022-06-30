from typing import Dict, Text
from unittest.case import skip
from unittest.mock import Mock, patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.forms.models import model_to_dict
from django.test import TestCase
from django_dynamic_fixture import G
from guardian.shortcuts import assign_perm
from parameterized import parameterized

from accounts.models import User
from exp.views.mixins import StudyTypeMixin
from studies.forms import StudyCreateForm, StudyEditForm
from studies.models import Lab, Study, StudyType
from studies.permissions import LabPermission, StudyPermission


class StudyFormTestCase(TestCase):
    def setUp(self):
        self.study_admin = G(
            User, is_active=True, is_researcher=True, given_name="Researcher 1"
        )
        self.study_designer = G(
            User, is_active=True, is_researcher=True, given_name="Researcher 2"
        )
        self.main_lab = G(Lab, name="MIT", approved_to_test=True)
        self.main_lab.researchers.add(self.study_designer)
        self.main_lab.researchers.add(self.study_admin)
        self.main_lab.member_group.user_set.add(self.study_designer)
        self.main_lab.member_group.user_set.add(self.study_admin)
        self.main_lab.save()

        # Researchers have same roles in second lab
        self.second_lab = G(Lab, name="Harvard", approved_to_test=True)
        self.second_lab.researchers.add(self.study_designer)
        self.second_lab.researchers.add(self.study_admin)
        self.second_lab.member_group.user_set.add(self.study_designer)
        self.second_lab.member_group.user_set.add(self.study_admin)
        self.second_lab.save()

        # Study admin does not have permissiont to move study to this lab
        self.other_lab = G(Lab, name="Caltech", approved_to_test=True)
        self.other_lab.researchers.add(self.study_admin)
        self.other_lab.readonly_group.user_set.add(self.study_admin)
        self.other_lab.save()

        self.study_type = G(StudyType, name="default", id=1)
        self.other_study_type = G(StudyType, name="other", id=2)
        self.nonexistent_study_type_id = 999

        self.generator_function_string = (
            "function(child, pastSessions) {return {frames: {}, sequence: []};}"
        )
        self.structure_string = (
            "some exact text that should be displayed in place of the loaded structure"
        )
        self.study = G(
            Study,
            image=SimpleUploadedFile(
                "fake_image.png", b"fake-stuff", content_type="image/png"
            ),  # we could also pass fill_nullable_fields=True
            # See: https://django-dynamic-fixture.readthedocs.io/en/latest/data.html#fill-nullable-fields
            creator=self.study_admin,
            shared_preview=False,
            study_type=self.study_type,
            name="Test Study",
            lab=self.main_lab,
            criteria_expression="",
            structure={
                "frames": {"frame-a": {}, "frame-b": {}},
                "sequence": ["frame-a", "frame-b"],
                "exact_text": self.structure_string,
            },
            use_generator=False,
            generator=self.generator_function_string,
            metadata={
                "player_repo_url": "https://github.com/lookit/ember-lookit-frameplayer",
                "last_known_player_sha": "fakecommitsha",
            },
            built=True,
        )
        self.study.admin_group.user_set.add(self.study_admin)
        self.study.design_group.user_set.add(self.study_designer)
        self.study.save()
        self.age_error_message = "The maximum age must be greater than the minimum age."

    def test_valid_structure_accepted(self):
        data = model_to_dict(self.study)
        structure_text = """{
            "frames": {"frame-a": {}, "frame-b": {}}, 
            "sequence": ["frame-a", "frame-b"]
        }"""
        data["structure"] = structure_text
        form = StudyEditForm(data=data, instance=self.study, user=self.study_designer)
        self.assertNotIn("structure", form.errors)
        form.is_valid()
        self.assertDictEqual(
            form.cleaned_data["structure"],
            {
                "frames": {"frame-a": {}, "frame-b": {}},
                "sequence": ["frame-a", "frame-b"],
                "exact_text": structure_text,
            },
        )

    def test_structure_with_extra_comma_invalid(self):
        data = model_to_dict(self.study)
        data[
            "structure"
        ] = """
            {
                "frames": {"frame-a": {}, "frame-b": {}}, 
                "sequence": ["frame-a", "frame-b"],
            }
            """
        form = StudyEditForm(data=data, instance=self.study, user=self.study_designer)
        self.assertIn("structure", form.errors)

    def test_empty_structure_invalid(self):
        data = model_to_dict(self.study)
        data["structure"] = ""
        form = StudyEditForm(data=data, instance=self.study, user=self.study_designer)
        self.assertIn("structure", form.errors)

    def test_valid_criteria_expression(self):
        data = model_to_dict(self.study)
        data["criteria_expression"] = (
            "((deaf OR hearing_impairment) OR NOT speaks_en) "
            "AND "
            "(age_in_days >= 365 AND age_in_days <= 1095)"
        )
        form = StudyEditForm(data=data, instance=self.study, user=self.study_designer)
        self.assertNotIn("criteria_expression", form.errors)

    def test_criteria_expression_with_extra_comma(self):
        data = model_to_dict(self.study)
        data["criteria_expression"] = (
            "((deaf OR hearing_impairment) OR NOT speaks_en)) "
            "AND "
            "(age_in_days >= 365 AND age_in_days <= 1095)"
        )
        form = StudyEditForm(data=data, instance=self.study, user=self.study_designer)
        self.assertIn("criteria_expression", form.errors)

    def test_criteria_expression_with_fake_token(self):
        data = model_to_dict(self.study)
        data["criteria_expression"] = (
            "((deaf OR hearing_impairment) OR NOT speaks_esperanto)) "
            "AND "
            "(age_in_days >= 365 AND age_in_days <= 1095)"
        )
        form = StudyEditForm(data=data, instance=self.study, user=self.study_designer)
        self.assertIn("criteria_expression", form.errors)

    def test_required_fields_cannot_be_empty(self):
        empty_field_values = {
            "name": "",
            "short_description": "",
            "purpose": "",
            "criteria": "",
            "duration": "",
            "contact_info": "",
        }
        for field_name, empty_value in empty_field_values.items():
            data = model_to_dict(self.study)
            data[field_name] = empty_value
            form = StudyEditForm(
                data=data, instance=self.study, user=self.study_designer
            )
            self.assertIn(field_name, form.errors)
            self.assertIn("This field is required.", form.errors[field_name])

    def test_non_required_fields_can_be_empty(self):
        empty_field_values = {
            "image": None,
            "compensation_description": "",
            "generator": "",
            "criteria_description": "",
        }
        for field_name, empty_value in empty_field_values.items():
            data = model_to_dict(self.study)
            data[field_name] = empty_value
            form = StudyEditForm(
                data=data, instance=self.study, user=self.study_designer
            )
            self.assertNotIn(field_name, form.errors)

    def test_standard_age_range_okay(self):
        data = model_to_dict(self.study)
        data["min_age_years"] = 1
        data["min_age_months"] = 0
        data["min_age_days"] = 0
        data["max_age_years"] = 2
        data["max_age_months"] = 0
        data["max_age_days"] = 0
        form = StudyEditForm(data=data, instance=self.study, user=self.study_designer)
        self.assertNotIn(self.age_error_message, form.non_field_errors())

    def test_inverted_age_range_invalid(self):
        data = model_to_dict(self.study)
        data["min_age_years"] = 2
        data["min_age_months"] = 0
        data["min_age_days"] = 0
        data["max_age_years"] = 1
        data["max_age_months"] = 0
        data["max_age_days"] = 0
        form = StudyEditForm(data=data, instance=self.study, user=self.study_designer)
        self.assertIn(self.age_error_message, form.non_field_errors())

    def test_age_range_validation_uses_30_day_month_definition(self):
        data = model_to_dict(self.study)
        data["min_age_years"] = 0
        data["min_age_months"] = 11
        data[
            "min_age_days"
        ] = 31  # Min age 361 days per usual definitions; 365.6 if month = 365/12
        data["max_age_years"] = 1
        data["max_age_months"] = 0
        data["max_age_days"] = 0
        form = StudyEditForm(data=data, instance=self.study, user=self.study_designer)
        self.assertNotIn(self.age_error_message, form.non_field_errors())

    def test_change_study_type(self):
        data = model_to_dict(self.study)
        data["study_type"] = self.other_study_type.id
        form = StudyEditForm(data=data, instance=self.study, user=self.study_designer)
        self.assertNotIn("study_type", form.errors)

    @skip("Removed study type change in study view")
    def test_study_type_to_nonexistent(self):
        data = model_to_dict(self.study)
        data["study_type"] = self.nonexistent_study_type_id
        form = StudyEditForm(data=data, instance=self.study, user=self.study_designer)
        self.assertIn(
            "Select a valid choice. That choice is not one of the available choices.",
            form.errors["study_type"],
        )

    def test_change_lab_without_perms(self):
        data = model_to_dict(self.study)
        data["lab"] = self.second_lab.id
        form = StudyEditForm(data=data, instance=self.study, user=self.study_designer)
        # make sure clean is actually called before moving on!
        form.is_valid()
        # Field is disabled, rather than limiting options, so just check cleaned data is unchanged
        self.assertEqual(form.cleaned_data["lab"].id, self.study.lab.id)

    def test_change_lab_with_perms(self):
        data = model_to_dict(self.study)
        data["lab"] = self.second_lab.id
        form = StudyEditForm(data=data, instance=self.study, user=self.study_admin)
        # make sure clean is actually called before moving on!
        form.is_valid()
        self.assertEqual(form.cleaned_data["lab"].id, self.second_lab.id)
        self.assertNotIn("lab", form.errors)

    def test_change_to_invalid_lab(self):
        data = model_to_dict(self.study)
        data["lab"] = self.other_lab.id
        form = StudyEditForm(data=data, instance=self.study, user=self.study_admin)
        form.is_valid()
        self.assertIn("lab", form.errors)
        self.assertIn(
            "Select a valid choice. That choice is not one of the available choices.",
            form.errors["lab"],
        )

    def test_create_study_in_valid_lab(self):
        data = model_to_dict(self.study)
        data["lab"] = self.main_lab.id
        form = StudyCreateForm(data=data, user=self.study_admin)
        form.is_valid()
        self.assertNotIn("lab", form.errors)

    def test_create_study_in_invalid_lab(self):
        data = model_to_dict(self.study)
        data["lab"] = self.other_lab.id
        form = StudyCreateForm(data=data, user=self.study_admin)
        form.is_valid()
        self.assertIn("lab", form.errors)
        self.assertIn(
            "Select a valid choice. That choice is not one of the available choices.",
            form.errors["lab"],
        )

    def test_lab_options_as_superuser(self):
        data = model_to_dict(self.study)
        su = G(
            User,
            is_active=True,
            is_researcher=True,
            given_name="super researcher",
            is_superuser=True,
        )

        create_form = StudyCreateForm(data=data, user=su)
        self.assertFalse(
            create_form.fields["lab"].disabled,
            "Lab selection is disabled on study create form for superuser",
        )
        self.assertEqual(
            create_form.fields["lab"].queryset.count(),
            Lab.objects.count(),
            "Superuser does not have all labs available in study create form",
        )
        self.assertNotIn("lab", create_form.errors)

        edit_form = StudyEditForm(data=data, instance=self.study, user=su)
        self.assertFalse(
            edit_form.fields["lab"].disabled,
            "Lab selection is disabled on study edit form for superuser",
        )
        self.assertEqual(
            edit_form.fields["lab"].queryset.count(),
            Lab.objects.count(),
            "Superuser does not have all labs available in study edit form",
        )
        self.assertNotIn("lab", edit_form.errors)

    def test_lab_options_as_user_with_sitewide_perm(self):
        data = model_to_dict(self.study)
        admin = G(
            User, is_active=True, is_researcher=True, given_name="super researcher"
        )
        assign_perm(LabPermission.CREATE_LAB_ASSOCIATED_STUDY.prefixed_codename, admin)
        self.main_lab.member_group.user_set.add(
            admin
        )  # Make a member of the study's lab
        self.study.design_group.user_set.add(
            admin
        )  # Allowed to edit this study in general (not necessarily lab)

        # If can create study in any lab, should see all labs as options when creating NEW study
        create_form = StudyCreateForm(data=data, user=admin)
        self.assertFalse(
            create_form.fields["lab"].disabled,
            "Lab selection is disabled on study create form for user with permission to create study in any lab",
        )
        self.assertEqual(
            create_form.fields["lab"].queryset.count(),
            Lab.objects.count(),
            "User with permission to create study in any lab does not have all labs available in study create form",
        )
        self.assertNotIn("lab", create_form.errors)

        # If can create study in any lab, should only see all labs as options when EDITING if has perm to change lab
        edit_form = StudyEditForm(data=data, instance=self.study, user=admin)
        self.assertTrue(
            edit_form.fields["lab"].disabled,
            "Lab selection is enabled on study edit form for user with permission to create study in any lab, but not permission to edit lab for this study",
        )
        self.assertEqual(
            edit_form.fields["lab"].queryset.count(),
            1,
            "User without permission to edit lab for this study should only have one option for lab on study edit form",
        )
        self.assertNotIn("lab", edit_form.errors)

        assign_perm(StudyPermission.CHANGE_STUDY_LAB.codename, admin, self.study)
        edit_form = StudyEditForm(data=data, instance=self.study, user=admin)
        self.assertFalse(
            edit_form.fields["lab"].disabled,
            "Lab selection is disabled on study edit form for user with permission to change lab",
        )
        self.assertEqual(
            edit_form.fields["lab"].queryset.count(),
            Lab.objects.count(),
            "User with permission to change lab for a study and to create study in lab does not see all labs as options to edit",
        )

    def test_lab_options_as_user_who_can_create_studies_in_two_labs(self):
        data = model_to_dict(self.study)
        researcher = G(
            User, is_active=True, is_researcher=True, given_name="super researcher"
        )
        assign_perm(
            LabPermission.CREATE_LAB_ASSOCIATED_STUDY.codename,
            researcher,
            self.main_lab,
        )
        assign_perm(
            LabPermission.CREATE_LAB_ASSOCIATED_STUDY.codename,
            researcher,
            self.second_lab,
        )
        self.main_lab.member_group.user_set.add(
            researcher
        )  # Make a member of the study's lab
        self.study.design_group.user_set.add(
            researcher
        )  # Allowed to edit this study in general (not necessarily lab)

        # If can create study in two labs + Sandbox, should see three labs as options when creating NEW study
        create_form = StudyCreateForm(data=data, user=researcher)
        self.assertFalse(
            create_form.fields["lab"].disabled,
            "Lab selection is disabled on study create form for user with permission to create study in two labs",
        )
        self.assertEqual(
            create_form.fields["lab"].queryset.count(),
            3,
            "User with permission to create study in any two labs does not see two labs as options when creating study",
        )
        self.assertIn(self.main_lab, create_form.fields["lab"].queryset)
        self.assertIn(self.second_lab, create_form.fields["lab"].queryset)
        self.assertNotIn(self.other_lab, create_form.fields["lab"].queryset)
        self.assertNotIn("lab", create_form.errors)

        # If can create study in two labs + Sandbox, and can edit this study's lab, should only see 3 options when editing
        assign_perm(StudyPermission.CHANGE_STUDY_LAB.codename, researcher, self.study)
        edit_form = StudyEditForm(data=data, instance=self.study, user=researcher)
        self.assertFalse(
            edit_form.fields["lab"].disabled,
            "Lab selection is disabled on study edit form for user with permission to change lab",
        )
        self.assertEqual(
            edit_form.fields["lab"].queryset.count(),
            3,
            "User with permission to change lab for a study and to create study in three labs does not see three labs as options to edit",
        )
        self.assertIn(self.main_lab, edit_form.fields["lab"].queryset)
        self.assertIn(self.second_lab, edit_form.fields["lab"].queryset)
        self.assertNotIn(self.other_lab, edit_form.fields["lab"].queryset)
        self.assertNotIn("lab", edit_form.errors)

    def test_scheduled_checkbox_enabled(self):
        """Checking that the Study Edit Form's sheduled field is always enabled.  JavaScript will disable this field when study is internal."""
        data = model_to_dict(self.study)
        structure_text = '{"frames": {"frame-a": {}, "frame-b": {}}, "sequence": ["frame-a", "frame-b"]}'
        data["structure"] = structure_text
        form = StudyEditForm(data=data, instance=self.study, user=self.study_designer)
        self.assertFalse(form.fields["scheduled"].disabled)


class StudyMixinsTestCase(TestCase):
    @parameterized.expand(
        [
            ("", "", False, "", "", "", ""),
            ("", "on", True, "scheduling value", "", "study platform value", ""),
            ("https://lookit.mit.edu", "", False, "", "", "", ""),
            (
                "https://lookit.mit.edu",
                "on",
                True,
                "Other",
                "Other value",
                "Other",
                "Other value",
            ),
        ]
    )
    @patch.object(StudyTypeMixin, "request", create=True)
    def test_validate_and_fetch_metadata(
        self,
        url: Text,
        post_scheduled: Text,
        meta_scheduled: bool,
        scheduling: Text,
        other_scheduling: Text,
        study_platform: Text,
        other_study_platform: Text,
        mock_request: Mock,
    ):
        type(mock_request).POST = expected_metadata = {
            "url": url,
            "scheduled": post_scheduled,
            "scheduling": scheduling,
            "other_scheduling": other_scheduling,
            "study_platform": study_platform,
            "other_study_platform": other_study_platform,
        }
        external = StudyType.get_external()
        metadata, errors = StudyTypeMixin().validate_and_fetch_metadata(external)

        expected_metadata["scheduled"] = meta_scheduled

        self.assertFalse(errors)
        self.assertEqual(expected_metadata, metadata)

    @parameterized.expand(
        [
            ({},),
            ({"scheduled": False},),
            ({"scheduled": True},),
        ]
    )
    @patch.object(StudyTypeMixin, "request", create=True)
    def test_validate_and_fetch_metadata_invalid_metadata(
        self, post_data: Dict, mock_request: Mock
    ):
        type(mock_request).POST = post_data
        external = StudyType.get_external()
        _, errors = StudyTypeMixin().validate_and_fetch_metadata(external)
        self.assertTrue(errors)
