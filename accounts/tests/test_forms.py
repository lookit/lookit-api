from django.test import TestCase

from accounts.forms import StudyListSearchForm


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
