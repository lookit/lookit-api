from django.test import SimpleTestCase

from studies.fields import CONDITIONS

# Each condition's position in CONDITIONS is its bit in Child.existing_conditions,
# so these positions map directly onto the stored data. This list is a fixed copy:
# do not regenerate it from CONDITIONS because we need to check that CONDITIONS
# has not changed.
#
# Adding a condition: append it to the end of the active entries in CONDITIONS
# (studies/fields.py) and to the end of this list. Never insert, remove or reorder
# entries.
LOCKED_CONDITION_ORDER = [
    "autism_spectrum_disorder", "deaf", "hearing_impairment", "dyslexia",  # 0-3
    "multiple_birth",  # 4
]  # fmt: skip


class ConditionOrderTestCase(SimpleTestCase):
    def test_existing_condition_positions_unchanged(self):
        codes = [code for code, _ in CONDITIONS]
        self.assertEqual(
            codes[: len(LOCKED_CONDITION_ORDER)],
            LOCKED_CONDITION_ORDER,
            "Existing entries in CONDITIONS were inserted, removed, or reordered. "
            "This changes the meaning of conditions already saved for children. "
            "Only append new conditions to the end of CONDITIONS.",
        )

    def test_new_conditions_added_to_locked_list(self):
        codes = [code for code, _ in CONDITIONS]
        self.assertEqual(
            codes[len(LOCKED_CONDITION_ORDER) :],
            [],
            "New conditions were appended to CONDITIONS. Append them to the end of "
            "LOCKED_CONDITION_ORDER too, so their positions are protected.",
        )

    def test_conditions_fit_in_bitfield(self):
        # django-bitfield allows at most 63 flags in a BigIntegerField.
        self.assertLessEqual(len(CONDITIONS), 63)
