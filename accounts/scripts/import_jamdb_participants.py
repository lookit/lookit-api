import json

from django.apps import apps

"""
This script is for migrating users from Lookit v1 to Lookit v2.  For each user in the old data, a user is created,
demographic data is created, and all associated children are created.

For users that have duplicate emails, these accounts are merged into one.  The original data is preserved by creating multiple
versions of demographic data for the merged user, and assigning all related children to the one merged user. Original ids are preserved under
the linked_former_lookit_ids field.
"""
users_created = 0
children_created = 0
demographic_data_created = 0


def get_participant_json():
    """
    Loads JSON file with participants from Lookit v1
    """
    try:
        with open("../participants.json") as data_file:
            data = json.load(data_file)
        return data
    except Exception:
        print("../participants.json does not exist. Quitting...")
        return


def get_duplicate_emails(participants):
    """
    Creates a list of duplicate emails in the db.  Emails need to be unique, so these users will be handled separately.
    """
    email_list = []
    for participant in participants:
        email_list.append(participant.get("attributes").get("email"))
    return [email for email in email_list if email_list.count(email) > 1]


def migrate_participants():
    """
    Maps Lookit V1 participants to new db
    """
    participants = get_participant_json()
    if not participants:
        print("No participants.json file.  This is for production only.")
        return
    duplicates = get_duplicate_emails(participants)
    print("Starting migration of old lookit participants...")
    part_count = 0
    unique_duplicates = set(duplicates)
    duplicate_participants = []
    for participant in participants:
        part_count += 1
        if participant.get("attributes").get("email") not in unique_duplicates:
            print(f"Examining participant {part_count}/{len(participants)}")
            create_participant(participant, apps)
        else:
            duplicate_participants.append(participant)
            print(f"Skipping participant {part_count}/{len(participants)}")

    duplicate_summary = handle_duplicate_emails(duplicate_participants, apps)

    print("========================================")
    print(f"Total original participants: {len(participants)}")
    print(
        f"{len(duplicates)} original participants with duplicate emails, for a total of {len(unique_duplicates)} duplicate emails "
    )
    print(
        f"Total users copied: {len(participants)} - {len(duplicates)} + {len(unique_duplicates)} merged accounts = {str(users_created)}"
    )
    print(f"Total demographics copied: {str(demographic_data_created)}")
    print(f"Total children copied: {str(children_created)}")
    print("========================================")
    print("Merged accounts:")
    print(duplicate_summary)


def sort_duplicate_list(sorted_duplicates):
    """
    Splits list of users w/ duplicate emails into a list of lists, where each sublist is attached to one email
    """
    sorted_dup_group = []

    for index, part in enumerate(sorted_duplicates):
        if not index:
            sorted_dup_group.append([part])
        else:
            if (
                part["attributes"]["email"]
                == sorted_dup_group[-1][-1]["attributes"]["email"]
            ):
                sorted_dup_group[-1].append(part)
            else:
                sorted_dup_group.append([part])
    return sorted_dup_group


def handle_duplicate_emails(duplicate_participants, apps):
    """
    Handle duplicate emails by merging all related accounts into one.  All accounts' demographic data
    is saved as versions.  All children across the related email accounts are connected to the one merged account
    """
    print("Handling duplicate emails...")
    sorted_dup_group = sort_duplicate_list(
        sorted(duplicate_participants, key=lambda k: k["attributes"]["email"])
    )

    duplicate_summary = {}
    for group in sorted_dup_group:
        # Sort sublist on date modified, oldest first
        sorted_group = sorted(group, key=lambda k: k["meta"]["modified-on"])
        for index, s in enumerate(sorted_group):
            if not index:
                # For first user in email group, create it, along with demographics and children
                user = create_participant(s, apps)
                duplicate_summary[user.username] = [user.former_lookit_id]
            else:
                # For subsequent emails in email group, attach demographic information and
                # children to first user
                user.linked_former_lookit_ids.append(s.get("id"))
                duplicate_summary[user.username].append(s.get("id"))
                user.save()
                create_demographics(user, s, apps)
                for profile in s.get("attributes").get("profiles"):
                    create_child(user, profile, apps)
    return duplicate_summary


def format_gender(gender):
    """
    Maps gender from Lookit v1 to current gender, assuming "other or prefer not to answer" mapping to na
    """
    gender_mapping = {"male": "m", "female": "f", "other or prefer not to answer": "na"}
    return gender_mapping.get(gender, "")


def format_age_at_birth(age):
    """
    Old gestationalAgeAtBirth fields went above 40, but now we are capping at 40.
    """
    if age:
        try:
            int_age = int(age)
            if int_age >= 40:
                return "40>"
            return age
        except ValueError:
            return age
    else:
        return None


def create_child(user, profile, apps):
    """
    Creates child and links to user
    """
    Child = apps.get_model("accounts", "Child")
    profile.get("gender")
    birthday = profile.get("birthday")
    Child.objects.create(
        given_name=profile.get("firstName", ""),
        birthday=birthday.split("T")[0] if birthday else birthday,
        gender=format_gender(profile.get("gender")),
        age_at_birth=format_age_at_birth(profile.get("gestationalAgeAtBirth"))
        or pull_choice_value(profile.get("ageAtBirth"), "age_at_birth", apps, "Child"),
        additional_information=get_simple_field(profile.get("additionalInformation")),
        deleted=profile.get("deleted"),
        former_lookit_profile_id=profile.get("profileId"),
        user=user,
    )
    global children_created
    children_created += 1


def pull_choice_value(original_field_value, field_name, apps, model_name=None):
    """
    Map display name to value for storing in db
    """
    if original_field_value is None:
        return ""
    fetched_model = apps.get_model(
        "accounts", model_name if model_name else "DemographicData"
    )
    choices = fetched_model._meta.get_field(field_name).choices
    ret = []
    if isinstance(original_field_value, str):
        for choice in choices:
            if choice[1] == original_field_value:
                ret = choice[0]
    else:
        for choice in choices:
            for selected in original_field_value:
                if choice[1] == selected:
                    ret.append(choice[0])
    return ret


def get_simple_field(value):
    """
    Returns empty string if value is None, since many fields don't accept null values
    """
    return "" if value is None else value


def create_demographics(user, participant, apps):
    """
    Creates demographic data and attaches to user
    """
    # Looks like annual income used to be stored as a range, before individual values.  Store this old value in former_lookit_annual_income.
    # If salary matches current choices, then it's also stored in annual_income field.
    DemographicData = apps.get_model("accounts", "DemographicData")
    attributes = participant.get("attributes")
    income = get_simple_field(attributes.get("demographicsAnnualIncome"))

    DemographicData.objects.create(
        created_at=participant.get("meta").get("created-on"),
        number_of_children=get_simple_field(
            attributes.get("demographicsNumberOfChildren")
        ),
        child_birthdays=[
            birthday.split("T")[0] if birthday else birthday
            for birthday in attributes.get("demographicsChildBirthdays")
        ],
        languages_spoken_at_home=get_simple_field(
            attributes.get("demographicsLanguagesSpokenAtHome")
        ),
        number_of_guardians=pull_choice_value(
            attributes.get("demographicsNumberOfGuardians"), "number_of_guardians", apps
        ),
        number_of_guardians_explanation=get_simple_field(
            attributes.get("demographicsNumberOfGuardiansExplanation")
        ),
        race_identification=pull_choice_value(
            attributes.get("demographicsRaceIdentification"),
            "race_identification",
            apps,
        ),
        former_lookit_annual_income=income,
        annual_income=income
        if income and "$" not in income and " " not in income
        else "",
        age=pull_choice_value(attributes.get("demographicsAge"), "age", apps),
        gender=format_gender(attributes.get("demographicsGender")),
        education_level=pull_choice_value(
            attributes.get("demographicsEducationLevel"), "education_level", apps
        ),
        spouse_education_level=pull_choice_value(
            attributes.get("demographicsSpouseEducationLevel"),
            "spouse_education_level",
            apps,
        ),
        number_of_books=attributes.get("demographicsNumberOfBooks"),
        additional_comments=get_simple_field(
            attributes.get("demographicsAdditionalComments")
        ),
        country=get_simple_field(attributes.get("demographicsCountry", "")),
        state=get_simple_field(attributes.get("demographicsState", "")),
        density=get_simple_field(attributes.get("demographicsDensity", "")),
        lookit_referrer=get_simple_field(
            attributes.get("demographicsHowDidYouHear", "")
        ),
        user=user,
    )

    global demographic_data_created
    demographic_data_created += 1


def create_participant(participant, apps):
    """
    Creates user and then adds related children and demographic data
    """
    # Assumptions:
    # - Preprending bcrypt$ before password.
    # - Old email field is going into new username field
    # - Old name field is being stored under given_name
    # - Older username field is being stored under nickname
    # - Don't seem to be many email preferences in db?
    attributes = participant.get("attributes")
    user_model = apps.get_model("accounts", "User")
    old_name = get_simple_field(attributes.get("name"))
    user = user_model.objects.create(
        date_created=participant.get("meta").get("created-on"),
        username=attributes.get("email"),
        password="bcrypt$" + attributes.get("password"),
        former_lookit_id=participant.get("id"),
        nickname=(
            old_name
            if old_name
            else get_simple_field(participant.get("id").split(".")[-1])
        ),
        is_active=True,
        is_staff=False,
        is_researcher=False,
        email_next_session=attributes.get("emailPreferenceNextSession", True),
        email_new_studies=attributes.get("emailPreferenceNewStudies", True),
        email_study_updates=attributes.get("emailPreferenceResultsPublished", True),
        email_response_questions=attributes.get("emailPreferenceOptOut", True),
    )
    global users_created
    users_created += 1

    create_demographics(user, participant, apps)
    for profile in attributes.get("profiles"):
        create_child(user, profile, apps)
    return user


def reverse_func():
    """
    For unapplying migrations - removes participants, children, and demographic data from Lookitv1
    """
    User = apps.get_model("accounts", "User")
    Child = apps.get_model("accounts", "Child")
    DemographicData = apps.get_model("accounts", "DemographicData")

    users = User.objects.exclude(former_lookit_id__exact="")
    user_ids = users.values_list("id", flat=True)
    DemographicData.objects.filter(user_id__in=user_ids).delete()
    Child.objects.exclude(former_lookit_profile_id="").delete()
    users.delete()
