"""Fields constants - at the moment, just used for BitFields."""
from django.conf import settings

# General Flags
CONDITIONS = (
    ("autism_spectrum_disorder", "Autism Spectrum Disorder"),
    ("aspergers_syndrome", "Asperger's Syndrome"),
    ("down_syndrome", "Down Syndrome"),
    ("williams_syndrome", "Williams Syndrome"),
    ("stroke", "Stroke"),
    ("blind", "Blind"),
    ("visual_impairment", "Visual Impairment"),
    ("deaf", "Deaf"),
    ("hearing_impairment", "Hearing Impairment"),
    ("dyslexia", "Dyslexia"),
    (
        "attention_deficit_hyperactivity_disorder",
        "Attention Deficit/Hyperactivity Disorder",
    ),
    ("learning_disability", "Learning Disability"),
    ("generalized_anxiety_disorder", "Generalized Anxiety Disorder"),
    ("obsessive_compulsive_disorder", "Obsessive-Compulsive Disorder"),
    ("panic_disorder", "Panic Disorder"),
    ("post_traumatic_stress_disorder", "Post-Traumatic Stress Disorder"),
    ("social_phobia_social_anxiety_disorder", "Social Phobia/Social Anxiety Disorder"),
    ("depression", "Depression"),
    ("mood_disorder", "Mood Disorder"),
    ("allergies", "Allergies"),
    ("fetal_alcohol_syndrome", "Fetal Alcohol Syndrome"),
    ("epilepsy", "Epilepsy"),
)


MULTIPLE_BIRTH = (
    ("twin", "Twin"),
    ("triplet", "Triplet"),
    ("quadruplet", "Quadruplet"),
    ("quintuplet", "Quintuplet"),
    ("sextuplet", "Sextuplet"),
    ("septuplet", "Septuplet"),
    ("octuplet", "Octuplet"),
)


SPEAKS_LANGUAGES = tuple(
    (f"speaks_{lang_code}", f"Speaks {lang_name}")
    for lang_code, lang_name in settings.LANGUAGES
)
