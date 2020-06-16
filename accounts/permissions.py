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


class LabGroup(set, Enum):
    GUEST = {LabPermission.CREATE_LAB_ASSOCIATED_STUDY}
    READONLY = {LabPermission.READ_STUDY_DETAILS, LabPermission.READ_STUDY_PREVIEW_DATA}
    MEMBER = {
        LabPermission.CREATE_LAB_ASSOCIATED_STUDY,
        LabPermission.READ_LAB_RESEARCHERS,
        LabPermission.READ_STUDY_DETAILS,
        LabPermission.READ_STUDY_PREVIEW_DATA,
    }
    ADMIN = {
        # Umbrella permissions
        LabPermission.READ_STUDY_PREVIEW_DATA,
        LabPermission.WRITE_STUDY_DETAILS,
        LabPermission.CHANGE_STUDY_STATUS,
        LabPermission.MANAGE_STUDY_RESEARCHERS,
        # Lab-centric permissions
        LabPermission.CREATE_LAB_ASSOCIATED_STUDY,
        LabPermission.EDIT_LAB_METADATA,
        LabPermission.MANAGE_LAB_RESEARCHERS,
        LabPermission.READ_LAB_RESEARCHERS,
    }


# Groups (mainly for use in migrations)
class LookitGroup(set, Enum):
    # Mostly a placeholder until we flesh out Lookit-wide permissions for our staff/RAs.
    # Will probably eventually want a layer like Labs are above Studies - e.g.
    # ability to see all studies from all labs" or just all studies.
    # For now we largely rely on superuser perms
    LOOKIT_ADMIN = {LookitPermission.APPROVE_LABS, LookitPermission.REVIEW_STUDIES}


def _create_groups(
    model_instance, group_enum, group_class, perm_class, group_object_permission_model
):
    uuid_segment = str(model_instance.uuid)[:7]
    object_name = model_instance._meta.object_name
    unique_group_tag = (
        f"{object_name} :: {model_instance.name[:7]}... ({uuid_segment}...)"
    )

    for group_spec in group_enum:
        # Group name is going to be something like "READ :: Lab :: MIT (0235dfa...)
        group_name = f"{group_spec.name} :: {unique_group_tag}"
        group = group_class.objects.create(name=group_name)

        for permission_meta in group_spec.value:
            permission = perm_class.objects.get(codename=permission_meta.codename)

            group_object_permission_model.objects.create(
                content_object=model_instance, permission=permission, group=group
            )
            group.save()

        setattr(model_instance, f"{group_spec.name.lower()}_group", group)

    model_instance.save()
