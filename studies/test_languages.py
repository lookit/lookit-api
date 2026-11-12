from django.test import SimpleTestCase

from studies.fields import LANGUAGES

# Each language's position in LANGUAGES is its bit in Child.languages_spoken, so
# these positions map directly onto the stored data. This list is a fixed copy:
# do not regenerate it from LANGUAGES because we need to check that LANGUAGES
# has not changed.
#
# Adding a language: append it to the end of LANGUAGES (studies/fields.py) and
# to the end of this list. Never insert, remove or reorder entries.
LOCKED_LANGUAGE_ORDER = [
    "en", "am", "bn", "bho", "my", "ceb", "hne", "nl", "egy", "fr",  # 0-9
    "gan", "de", "gu", "hak", "ha", "he", "hi", "ig", "id", "pes",  # 10-19
    "it", "ja", "jv", "cjy", "kn", "km", "ko", "mag", "mai", "ms",  # 20-29
    "ml", "cmn", "mr", "nan", "mor", "pbu", "uzn", "or", "pl", "pt",  # 30-39
    "ro", "ru", "skr", "sd", "so", "es", "su", "tl", "ta", "te",  # 40-49
    "th", "tr", "uk", "ur", "vi", "lah", "wuu", "hsn", "yo", "yue",  # 50-59
    "cy", "hu",  # 60-61
]  # fmt: skip


class LanguageOrderTestCase(SimpleTestCase):
    def test_existing_language_positions_unchanged(self):
        codes = [code for code, _ in LANGUAGES]
        self.assertEqual(
            codes[: len(LOCKED_LANGUAGE_ORDER)],
            LOCKED_LANGUAGE_ORDER,
            "Existing entries in LANGUAGES were inserted, removed, or reordered. "
            "This changes the meaning of languages already saved for children. "
            "Only append new languages to the end of LANGUAGES.",
        )

    def test_new_languages_added_to_locked_list(self):
        codes = [code for code, _ in LANGUAGES]
        self.assertEqual(
            codes[len(LOCKED_LANGUAGE_ORDER) :],
            [],
            "New languages were appended to LANGUAGES. Append them to the end of "
            "LOCKED_LANGUAGE_ORDER too, so their positions are protected.",
        )

    def test_languages_fit_in_bitfield(self):
        # django-bitfield allows at most 63 flags in a BigIntegerField.
        self.assertLessEqual(len(LANGUAGES), 63)
