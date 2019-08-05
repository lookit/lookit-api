import datetime

from django.test import TestCase
from django_dynamic_fixture import G
from lark.exceptions import UnexpectedCharacters

from accounts.models import Child
from accounts.queries import get_child_eligibility
from studies.models import Study


class CriteriaExpressionTestCase(TestCase):
    def setUp(self):
        self.fake_study = G(Study)
        self.complex_condition = (
            "((deaf OR hearing_impairment) OR NOT speaks_en) "
            "AND "
            "(age_in_days >= 365 AND age_in_days <= 1095)"
        )
        self.malformed_condition = "deaf OR hearing_impaired OR multiple_birth"
        self.deaf_child = G(
            Child,
            existing_conditions=Child.existing_conditions.deaf,
            languages_spoken=Child.languages_spoken.en,
            birthday=datetime.date.today() - datetime.timedelta(days=3 * 365),
        )

        self.hearing_impaired_child = G(
            Child,
            existing_conditions=Child.existing_conditions.hearing_impairment,
            languages_spoken=Child.languages_spoken.en,
            birthday=datetime.date.today() - datetime.timedelta(days=3 * 365),
        )

        self.non_english_speaking_child = G(
            Child,
            existing_conditions=Child.existing_conditions.multiple_birth,
            languages_spoken=Child.languages_spoken.fr,
            birthday=datetime.date.today() - datetime.timedelta(days=3 * 365),
        )

        self.older_child = G(
            Child,
            existing_conditions=Child.existing_conditions.deaf,
            languages_spoken=Child.languages_spoken.en,
            birthday=datetime.date.today() - datetime.timedelta(days=10 * 365),
        )

    def test_simple_condition(self):
        self.assertTrue(get_child_eligibility(self.deaf_child, "deaf"))

    def test_complex_condition(self):
        self.assertTrue(get_child_eligibility(self.deaf_child, self.complex_condition))
        self.assertTrue(
            get_child_eligibility(self.hearing_impaired_child, self.complex_condition)
        )
        self.assertTrue(
            get_child_eligibility(
                self.non_english_speaking_child, self.complex_condition
            )
        )
        self.assertFalse(
            get_child_eligibility(self.older_child, self.complex_condition)
        )

    def test_parse_failure(self):
        self.assertRaises(
            UnexpectedCharacters,
            get_child_eligibility,
            self.deaf_child,
            self.malformed_condition,
        )
