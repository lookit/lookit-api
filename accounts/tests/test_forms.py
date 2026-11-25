import re

from django.test import TestCase

from accounts.forms import ChildForm, StudyListSearchForm
from accounts.models import Child
from studies.fields import LANGUAGES

LANGUAGE_CODES = [code for code, _ in LANGUAGES]


class StudyListSearchFormTestCase(TestCase):
    def test_none_child(self):
        form = StudyListSearchForm(data={})

        # Confirm form has no error and is valid
        self.assertFalse(form.errors)
        self.assertTrue(form.is_valid())

        # Remove child from cleaned data
        del form.cleaned_data["child"]

        # confirm clean doesn't throw an error
        self.assertTrue(form.clean())


class ChildFormLanguagesTestCase(TestCase):
    def test_widget_shows_english_first_then_alphabetical(self):
        choices = ChildForm().fields["languages_spoken"].widget.choices
        codes = [code for code, _ in choices]
        labels = [str(label).casefold() for _, label in choices[1:]]

        self.assertEqual(codes[0], "en")
        self.assertEqual(labels, sorted(labels))
        self.assertCountEqual(codes, LANGUAGE_CODES)

    def test_field_choices_keep_languages_bit_order(self):
        # BitFormField.clean() uses the position of each choice as its bit index,
        # so the field's own choices must stay in LANGUAGES order.
        choices = ChildForm().fields["languages_spoken"].choices
        self.assertEqual([code for code, _ in choices], LANGUAGE_CODES)

    def test_selected_languages_saved_to_correct_bits(self):
        selected = ["cy", "es", "hu", "yue"]
        expected = sum(1 << LANGUAGE_CODES.index(code) for code in selected)

        cleaned = ChildForm().fields["languages_spoken"].clean(selected)

        self.assertEqual(cleaned, expected)

    def test_existing_child_languages_rendered_as_checked(self):
        child = Child(
            languages_spoken=Child.languages_spoken.cy
            | Child.languages_spoken.es
            | Child.languages_spoken.yue
        )
        html = str(ChildForm(instance=child)["languages_spoken"])
        checked = set(re.findall(r'<input[^>]*value="([^"]+)"[^>]*checked', html))

        self.assertEqual(checked, {"cy", "es", "yue"})
