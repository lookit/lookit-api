import datetime
import json
from collections import Counter, defaultdict

from django.contrib.auth.mixins import UserPassesTestMixin
from django.core.paginator import Paginator
from django.core.serializers.json import DjangoJSONEncoder
from django.views import generic

from accounts.models import Child, User
from exp.utils import RESPONSE_PAGE_SIZE
from exp.views.mixins import ExperimenterLoginRequiredMixin
from studies.fields import (
    CONDITIONS,
    GESTATIONAL_AGE_ENUM_MAP,
    LANGUAGES,
    popcnt_bitfield,
)
from studies.models import Study
from studies.permissions import StudyPermission
from studies.queries import get_annotated_responses_qs, studies_for_which_user_has_perm

LANGUAGES_MAP = {code: lang for code, lang in LANGUAGES}
CONDITIONS_MAP = {snake_cased: title_cased for snake_cased, title_cased in CONDITIONS}


class StudyParticipantAnalyticsView(
    ExperimenterLoginRequiredMixin, UserPassesTestMixin, generic.TemplateView
):
    template_name = "studies/study_participant_analytics.html"
    model = Study
    raise_exception = True

    def can_see_analytics(self):
        return (
            self.request.user.has_perm("accounts.can_view_analytics")
            and self.request.user.is_researcher
        )

    test_func = can_see_analytics

    def get_context_data(self, **kwargs):
        """Context getter override."""
        ctx = super().get_context_data(**kwargs)

        if self.request.user.has_perm("studies.view_all_response_data_in_analytics"):
            # Recruitment manager
            studies_for_user = Study.objects.all()
            # Template tag needs a single object to check, so we need to flag based on queryset.
            ctx["can_view_all_responses"] = True
        else:
            # Researcher or other
            studies_for_user = studies_for_which_user_has_perm(
                self.request.user, StudyPermission.READ_STUDY_RESPONSE_DATA
            )

        # Responses for studies - only include real (non-preview) responses here
        annotated_responses = (
            get_annotated_responses_qs()
            .filter(study__in=studies_for_user, is_preview=False)
            .select_related("child", "child__user", "study", "demographic_snapshot")
        ).values(
            "uuid",
            "date_created",
            "current_ruling",
            "child_id",
            "child__uuid",
            "child__birthday",
            "child__gender",
            "child__gestational_age_at_birth",
            "child__languages_spoken",
            "study__name",
            "study_id",
            "child__user__uuid",
            "demographic_snapshot__number_of_children",
            "demographic_snapshot__race_identification",
            "demographic_snapshot__number_of_guardians",
            "demographic_snapshot__annual_income",
            "demographic_snapshot__age",
            "demographic_snapshot__education_level",
            "demographic_snapshot__gender",
            "demographic_snapshot__spouse_education_level",
            "demographic_snapshot__density",
            "demographic_snapshot__number_of_books",
            "demographic_snapshot__country",
            "demographic_snapshot__state",
            "demographic_snapshot__lookit_referrer",
            "demographic_snapshot__additional_comments",
        )

        # now, map studies for each child, and gather demographic data as well.
        studies_for_child = defaultdict(set)
        paginator = Paginator(annotated_responses, RESPONSE_PAGE_SIZE)
        for page_num in paginator.page_range:
            page_of_responses = paginator.page(page_num)
            for resp in page_of_responses:
                studies_for_child[resp["child_id"]].add(resp["study__name"])

            # Include _all_ non-researcher users on Lookit
        registrations = User.objects.filter(is_researcher=False).values_list(
            "date_created", flat=True
        )

        ctx["all_studies"] = studies_for_user

        ctx["registration_data"] = json.dumps(
            list(registrations), cls=DjangoJSONEncoder
        )

        if self.request.user.has_perm("accounts.can_view_all_children_in_analytics"):
            children_queryset = Child.objects.filter(user__is_researcher=False)
            ctx["can_view_all_children"] = True
        else:
            children_queryset = Child.objects.filter(
                user__is_researcher=False,
                id__in=annotated_responses.values_list(
                    "child_id", flat=True
                ).distinct(),
            )
        children_pivot_data = unstack_children(children_queryset, studies_for_child)

        flattened_responses = get_flattened_responses(
            annotated_responses, studies_for_child
        )

        ctx["response_timeseries_data"] = json.dumps(flattened_responses, default=str)

        ctx["studies"], ctx["languages"], ctx["characteristics"], ctx["ages"] = [
            dict(counter) for counter in children_pivot_data
        ]
        return ctx


def get_flattened_responses(response_qs, studies_for_child):
    """Get derived attributes for children.

    TODO: consider whether or not this work should be extracted out into a dataframe.
    """
    response_data = []
    paginator = Paginator(response_qs, RESPONSE_PAGE_SIZE)
    for page_num in paginator.page_range:
        page_of_responses = paginator.page(page_num)
        for resp in page_of_responses:
            participation_date = resp["date_created"]
            child_age_in_days = (
                resp["date_created"].date() - resp["child__birthday"]
            ).days
            languages_spoken = popcnt_bitfield(
                int(resp["child__languages_spoken"]), "languages"
            )
            response_data.append(
                {
                    "Response (unique identifier)": resp["uuid"],
                    "Child (unique identifier)": resp["child__uuid"],
                    "Child Age in Days": child_age_in_days,
                    "Child Age in Months": int(child_age_in_days // 30),
                    "Child Age in Years": int(child_age_in_days // 365),
                    "Child Gender": resp["child__gender"],
                    "Child Gestational Age at Birth": GESTATIONAL_AGE_ENUM_MAP.get(
                        resp["child__gestational_age_at_birth"], "Unknown"
                    ),
                    "Child # Languages Spoken": len(languages_spoken),
                    "Child # Studies Participated": len(
                        studies_for_child[resp["child_id"]]
                    ),
                    "Study": resp["study__name"],
                    "Study ID": resp["study_id"],  # TODO: change this to use UUID
                    "Family (unique identifier)": resp["child__user__uuid"],
                    "Family # of Children": resp[
                        "demographic_snapshot__number_of_children"
                    ],
                    "Family Race/Ethnicity": resp[
                        "demographic_snapshot__race_identification"
                    ],
                    "Family # of Guardians": resp[
                        "demographic_snapshot__number_of_guardians"
                    ],
                    "Family Annual Income": resp["demographic_snapshot__annual_income"],
                    "Parent/Guardian Age": resp["demographic_snapshot__age"],
                    "Parent/Guardian Education Level": resp[
                        "demographic_snapshot__education_level"
                    ],
                    "Parent/Guardian Gender": resp["demographic_snapshot__gender"],
                    "Parent/Guardian Spouse Educational Level": resp[
                        "demographic_snapshot__spouse_education_level"
                    ],
                    "Living Density": resp["demographic_snapshot__density"],
                    "Number of Books": resp["demographic_snapshot__number_of_books"],
                    "Country": resp["demographic_snapshot__country"],
                    "State": resp["demographic_snapshot__state"],
                    "Time of Response": resp["date_created"].isoformat(),
                    "Consent Ruling": resp["current_ruling"],
                    "Lookit Referrer": resp["demographic_snapshot__lookit_referrer"],
                    "Additional Comments": resp[
                        "demographic_snapshot__additional_comments"
                    ],
                }
            )

    return response_data


def unstack_children(children_queryset, studies_for_child_map):
    """Unstack spoken languages, characteristics/conditions, and parent races/ethnicities"""
    languages = Counter()
    characteristics = Counter()
    studies = Counter()
    ages = Counter()
    for child in children_queryset:
        for study_name in studies_for_child_map[child.id]:
            studies[study_name] += 1
        for lang in child.languages_spoken:
            if lang[1]:
                languages[LANGUAGES_MAP[lang[0]]] += 1
        for cond in child.existing_conditions:
            if cond[1]:
                characteristics[CONDITIONS_MAP[cond[0]]] += 1

        child_age_days = (
            (datetime.date.today() - child.birthday).days if child.birthday else None
        )

        if child_age_days:  # In the rare case that we don't have a child age
            child_age_months = child_age_days // 30
            if child_age_months == 1:
                child_age = "1 month"
            elif child_age_months < 24:
                child_age = str(child_age_months) + " months"
            elif child_age_months == 24:
                child_age = "2 years"
            else:
                child_age = str(child_age_days // 365) + " years"
        else:
            child_age = None

        ages[child_age] += 1

    return studies, languages, characteristics, ages
