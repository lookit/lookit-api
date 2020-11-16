"""Fields constants - at the moment, just used for BitFields."""
from django.utils.translation import gettext_lazy as _
from model_utils import Choices

# Conditions and Multiple birth are bitfield, NOT choices!
CONDITIONS = (
    ("autism_spectrum_disorder", _("Autism Spectrum Disorder")),
    ("deaf", _("Deaf")),
    ("hearing_impairment", _("Hard of Hearing")),
    ("dyslexia", _("Dyslexia")),
    ("multiple_birth", _("Multiple Birth (twin, triplet, or higher order)")),
    # ("aspergers_syndrome", "Asperger's Syndrome"),
    # ("down_syndrome", "Down Syndrome"),
    # ("williams_syndrome", "Williams Syndrome"),
    # ("stroke", "Stroke"),
    # ("blind", "Blind"),
    # ("visual_impairment", "Visual Impairment"),
    # (
    #     "attention_deficit_hyperactivity_disorder",
    #     "Attention Deficit/Hyperactivity Disorder",
    # ),
    # ("learning_disability", "Learning Disability"),
    # ("generalized_anxiety_disorder", "Generalized Anxiety Disorder"),
    # ("obsessive_compulsive_disorder", "Obsessive-Compulsive Disorder"),
    # ("panic_disorder", "Panic Disorder"),
    # ("post_traumatic_stress_disorder", "Post-Traumatic Stress Disorder"),
    # ("social_phobia_social_anxiety_disorder", "Social Phobia/Social Anxiety Disorder"),
    # ("depression", "Depression"),
    # ("other_mood_disorder", "Other Mood Disorder"),
    # ("allergies", "Allergies"),
    # ("fetal_alcohol_syndrome", "Fetal Alcohol Syndrome"),
    # ("epilepsy", "Epilepsy"),
    # ("diabetes", "Diabetes"),
    # ("other_chronic_medical_condition", "Other Chronic Medical Condition"),
    # ("other_genetic_condition", "Other Genetic Condition"),
    # ("gifted_advanced_learning_needs", "Gifted/Advanced learning needs"),
    # ("adopted", "Adopted"),
    # ("has_older_sibling", "Has at least one older sibling"),
    # ("has_younger_sibling", "Has at least one younger sibling"),
)


# Keeping for now, though this will probably not be needed.
MULTIPLE_BIRTH_CHOICES = Choices(
    ("twin", _("Twin")),
    ("triplet", _("Triplet")),
    ("quadruplet", _("Quadruplet")),
    ("quintuplet", _("Quintuplet")),
    ("sextuplet", _("Sextuplet")),
    ("septuplet", _("Septuplet")),
    ("octuplet", _("Octuplet")),
)


# Ranked by # of speakers globally, except English is on top.
LANGUAGES = (
    ("en", _("English")),
    ("am", _("Amharic")),
    ("bn", _("Bengali")),
    ("bho", _("Bhojpuri")),
    ("my", _("Burmese")),
    ("ceb", _("Cebuano")),
    ("hne", _("Chhattisgarhi")),
    ("nl", _("Dutch")),
    ("egy", _("Egyptian Spoken Arabic")),
    ("fr", _("French")),
    ("gan", _("Gan")),
    ("de", _("German")),
    ("gu", _("Gujarati")),
    ("hak", _("Hakka")),
    ("ha", _("Hausa")),
    ("hi", _("Hindi")),
    ("ig", _("Igbo")),
    ("id", _("Indonesian")),
    ("pes", _("Iranian Persian")),
    ("it", _("Italian")),
    ("ja", _("Japanese")),
    ("jv", _("Javanese")),
    ("cjy", _("Jinyu")),
    ("kn", _("Kannada")),
    ("km", _("Khmer")),
    ("ko", _("Korean")),
    ("mag", _("Magahi")),
    ("mai", _("Maithili")),
    ("ms", _("Malay")),
    ("ml", _("Malayalam")),
    ("cmn", _("Mandarin")),
    ("mr", _("Marathi")),
    ("nan", _("Min Nan")),
    ("mor", _("Moroccan Spoken Arabic")),
    ("pbu", _("Northern Pashto")),
    ("uzn", _("Northern Uzbek")),
    ("or", _("Odia")),
    ("pl", _("Polish")),
    ("pt", _("Portuguese")),
    ("ro", _("Romanian")),
    ("ru", _("Russian")),
    ("skr", _("Saraiki")),
    ("sd", _("Sindhi")),
    ("so", _("Somali")),
    ("es", _("Spanish")),
    ("su", _("Sunda")),
    ("tl", _("Tagalog")),
    ("ta", _("Tamil")),
    ("te", _("Telugu")),
    ("th", _("Thai")),
    ("tr", _("Turkish")),
    ("uk", _("Ukrainian")),
    ("ur", _("Urdu")),
    ("vi", _("Vietnamese")),
    ("lah", _("Western Punjabi")),
    ("wuu", _("Wu")),
    ("hsn", _("Xiang Chinese")),
    ("yo", _("Yoruba")),
    ("yue", _("Yue")),
)

# XXX: These are only *mostly* copied and pasted the corresponding choices in the Child model - do not try to
# create a single source of truth from these!
# As noted in studies/models.py, we want to enable the choice "Marked as N/A" (by participant) and have null be
# "Nothing specified." (by the experimenter generating the query model).
GENDER_OPTIONS = (
    (0, "na", _("Not answered")),
    (1, "o", _("Other")),
    (2, "m", _("Male")),
    (3, "f", _("Female")),
)

GENDER_CHOICES = Choices(*GENDER_OPTIONS)

# Element #1 == database representation, #2 == valid python identifier used in code, #3 == human readable version.
# See https://django-model-utils.readthedocs.io/en/latest/utilities.html#choices

DEFAULT_GESTATIONAL_AGE_OPTIONS = (
    (None, "no_answer", _("Not sure or prefer not to answer")),
    (0, "under_twenty_four_weeks", _("Under 24 weeks")),
    (1, "twenty_four_weeks", _("24 weeks")),
    (2, "twenty_five_weeks", _("25 weeks")),
    (3, "twenty_six_weeks", _("26 weeks")),
    (4, "twenty_seven_weeks", _("27 weeks")),
    (5, "twenty_eight_weeks", _("28 weeks")),
    (6, "twenty_nine_weeks", _("29 weeks")),
    (7, "thirty_weeks", _("30 weeks")),
    (8, "thirty_one_weeks", _("31 weeks")),
    (9, "thirty_two_weeks", _("32 weeks")),
    (10, "thirty_three_weeks", _("33 weeks")),
    (11, "thirty_four_weeks", _("34 weeks")),
    (12, "thirty_five_weeks", _("35 weeks")),
    (13, "thirty_six_weeks", _("36 weeks")),
    (14, "thirty_seven_weeks", _("37 weeks")),
    (15, "thirty_eight_weeks", _("38 weeks")),
    (16, "thirty_nine_weeks", _("39 weeks")),
    (17, "over_forty_weeks", _("40 or more weeks")),
)

GESTATIONAL_AGE_ENUM_MAP = {opt[0]: opt[2] for opt in DEFAULT_GESTATIONAL_AGE_OPTIONS}

GESTATIONAL_AGE_CHOICES = Choices(*DEFAULT_GESTATIONAL_AGE_OPTIONS)

# No null values for filters - must explicitly include N/A in the query model itself since we are dealing with a
# range of (enumerated) values.
GESTATIONAL_AGE_FILTER_CHOICES = Choices(*DEFAULT_GESTATIONAL_AGE_OPTIONS[1:])


def popcnt_bitfield(integer, field_type):
    selected = []
    if field_type.lower() == "languages":
        bitfield_items = LANGUAGES
    elif field_type.lower() == "conditions":
        bitfield_items = CONDITIONS
    else:
        raise RuntimeError(f"Unsupported fieldtype: {field_type}")
    for bit_index in range(64):
        if (2 ** bit_index) & integer:
            selected.append(bitfield_items[bit_index])

    return selected
