"""
Permissions for Lookit-wide groups; minimal now but a placeholder for where
we can flesh out permissions for e.g. RAs working on tech support vs. recruitment.
Codenames used here are NOT directly in line with model/study level perms used elsewhere
for ease of avoiding conflicts and removing these permissions later.
"""
from collections import namedtuple
from enum import Enum

from studies.models import Lab, Study
from django.contrib.contenttypes.models import ContentType

SimplePermissionSpec = namedtuple(
    "SimplePermissionSpec", ["codename", "name", "content_type", "description"]
)


class LookitPermission(Enum):
    APPROVE_LABS = SimplePermissionSpec(
        codename="lookit__approve_labs",
        name="Can change lab.approved_to_test for any lab",
        content_type=ContentType.objects.get_for_model(Lab),
        description="Approve a lab that has been created on Lookit",
    )
    REVIEW_STUDIES = SimplePermissionSpec(
        codename="lookit__review_studies",
        name="Can approve and reject all studies",
        content_type=ContentType.objects.get_for_model(Study),
        description="Can approve or reject submitted studies on Lookit",
    )


# Groups (mainly for use in migrations)
class LookitGroup(set, Enum):
    # Mostly a placeholder until we flesh out Lookit-wide permissions for our staff/RAs.
    # Will probably eventually want a layer like Labs are above Studies - e.g.
    # ability to see all studies from all labs" or just all studies.
    # For now we largely rely on superuser perms
    LOOKIT_ADMIN = {LookitPermission.APPROVE_LABS, LookitPermission.REVIEW_STUDIES}
