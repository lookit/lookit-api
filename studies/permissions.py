"""
Data structures & functions for the object-based permissions in Lookit.

These must be defined *outside* of the database/guardian tables for two
purposes:
1) serving as a source of truth,
and
2) usage in migrations.

We are using naming conventions that build upon that set by Django itself,
while adding some structural and syntactical elements that help us reason
about permissions in a more queryset-centric way.

As of 2.0, the default per-model permissions added by django.contrib.auth
include:

- ${app_name}.add_${model}
- ${app_name}.change_${model}
- ${app_name}.delete_${model}
- ${app_name}.view_${model}

To enhance this while still leveraging the generated defaults, we have
a few additional field-specific conventions.

- ${app_name}.edit_${model}__${field}
- ${app_name}.read_${model}__${field}

In this context, "Edit" is analogous to "Change", but restricted to a single
field within the specified model. Similarly, "Read" is analogous to "View"
for a single field within a model.

If the specified field is a relationship of some kind (OneToOne, ForeignKey,
etc.) then the model-level variant of the permission (i.e. "Change" or "View")
applies, but only to the *related* model instance(s). The "dunder" syntax should
feel familiar from querysets, and allows for for arbitrary nesting as such:

- ${app_name}.read_${model}__${field}__${subfield}__...

and even filters, using postfixed parenthetical key-value pairs:

read_study__responses(is_preview=True)

The final subfield may have or'd regex-like syntax for multiple fields,
like so:

read_study__[name|public|state|min_age_years|max_age_years|...]

To complete the correspondence between per-model and per-object permissions,
we need two additional field-level permissions to associate and dissociate
existing instances of the relation's specified model.

- ${app_name}.associate_${model}__${field}
- ${app_name}.dissociate_${model}__${field}

This allows us to be MECE with the "Add" and "Delete" permissions of the
related model.

There will be the occasional case where we wish to specify data that is
either a composite of many fields, or some kind of summary data.
Given the 100 char max length of Permission, we can't list too many
fields or a complex queryset serialization, so there's the choice
of arbitrary delimiters in ANGRY_SNAKE_CASE, caret-delimited style:

read_study__<ANALYTICS>
read_study__<DETAILS>

This gives the permission author the flexibility to "kick the can down the
road" in terms of properly segmenting permissions, or represent things
that simply aren't modeled in the database.
"""

from enum import Enum
from typing import NamedTuple, Tuple


class _PermissionName(Enum):
    # Model-level
    ADD = "add"
    CHANGE = "change"
    DELETE = "delete"
    VIEW = "view"
    # Field-level
    EDIT = "edit"
    READ = "read"
    ASSOCIATE = "associate"
    DISSOCIATE = "dissociate"


class _PermissionParts(NamedTuple):
    permission: str
    model_name: str
    relationship_path: Tuple[str, ...]
    target_fields: Tuple[str, ...]


def _make_permission_meta_for_app(app_name: str):
    """
    Construct a _PermissionMeta class for this app. The app_name is not simply defined
    as a field because then it would be included when iterating over the tuple, breaking
    use of this as a wrapper for permissions as defined on models.

    TODO: upgrade to python 3.8 and use cachedproperty decorator
    """

    class _PermissionMeta(NamedTuple):
        """Immutable, object-oriented wrapper for Study and Lab permissions.

        We exploit the fact that private fields are not returned when iterating
        over tuples.

        Properties:
            codename: a string codename. See module docstring for conventions.
            description: a string description.
        """

        codename: str
        description: str

        @property
        def parts(self) -> _PermissionParts:
            perm_and_model, *field_vector = self.codename.split("__")
            permission, model_name = perm_and_model.split("_")

            if field_vector:
                final_field_spec = field_vector.pop()
                target_fields = tuple(final_field_spec.strip("[]").split("|"))
            else:
                target_fields = ()

            return _PermissionParts(
                permission=permission,
                model_name=model_name,
                relationship_path=tuple(field_vector),
                target_fields=target_fields,
            )

        @property
        def prefixed_codename(self) -> str:
            return app_name + "." + self.codename

        @property
        def permission(self) -> str:
            return self.parts.permission

        @property
        def model_name(self) -> str:
            return self.parts.model_name

        @property
        def relationship_path(self) -> Tuple[str, ...]:
            return self.parts.relationship_path

        @property
        def target_fields(self) -> Tuple[str, ...]:
            return self.parts.target_fields

        @classmethod
        def from_parts(
            cls,
            permission: str,
            model_name: str,
            relationship_path: Tuple[str, ...],
            target_fields: Tuple[str, ...],
            description: str,
        ):
            codename = f"{permission}_{model_name}"
            if relationship_path:
                codename += f"__{'__'.join(relationship_path)}"
            if target_fields:
                if len(target_fields) > 1:
                    codename += f"__[{'|'.join(target_fields)}]"
                else:
                    codename += f"__{target_fields[0]}"

            return cls(codename, description)

    return _PermissionMeta


_PermissionMetaStudiesApp = _make_permission_meta_for_app("studies")


def create_groups_for_instance(
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


def create_lab_version(study_permission: _PermissionMetaStudiesApp):
    permission, model_name, relationship_path, target_fields = study_permission.parts
    if model_name == "lab":
        raise TypeError("This permission is already lab specific!")

    description = study_permission.description

    relationship_path = (model_name,) + relationship_path

    return _PermissionMetaStudiesApp.from_parts(
        permission,
        "lab",
        relationship_path,
        target_fields,
        f"{description} (for all studies in the lab)",
    )


class StudyPermission(_PermissionMetaStudiesApp, Enum):
    READ_STUDY_DETAILS = _PermissionMetaStudiesApp(
        codename="read_study__<DETAILS>",
        description="Read study details and preview study",
    )
    WRITE_STUDY_DETAILS = _PermissionMetaStudiesApp(
        codename="edit_study__<DETAILS>", description="Write study details"
    )
    CHANGE_STUDY_STATUS = _PermissionMetaStudiesApp(
        codename="edit_study__status", description="Change study status"
    )
    MANAGE_STUDY_RESEARCHERS = _PermissionMetaStudiesApp(
        codename="edit_study__<GROUP>__user_set", description="Manage study researchers"
    )
    READ_STUDY_RESPONSE_DATA = _PermissionMetaStudiesApp(
        codename="read_study__responses",
        description="View/download study response data",
    )
    READ_STUDY_PREVIEW_DATA = _PermissionMetaStudiesApp(
        codename="read_study__responses(is_preview=True)",
        description="View/download preview data",
    )
    CODE_STUDY_CONSENT = _PermissionMetaStudiesApp(
        codename="edit_study__responses__consent_rulings",
        description="Code consent for study",
    )
    CODE_STUDY_PREVIEW_CONSENT = _PermissionMetaStudiesApp(
        codename="edit_study__responses__consent_rulings(is_preview=True)",
        description="Code consent for preview responses only",
    )
    CONTACT_STUDY_PARTICIPANTS = _PermissionMetaStudiesApp(
        codename="edit_study__message_set", description="Contact participants for study"
    )
    EDIT_STUDY_FEEDBACK = _PermissionMetaStudiesApp(
        codename="edit_study__feedback", description="Edit feedback for study"
    )
    CHANGE_STUDY_LAB = _PermissionMetaStudiesApp(
        codename="edit_study__lab", description="Change the associated lab for study"
    )
    DELETE_ALL_PREVIEW_DATA = _PermissionMetaStudiesApp(
        codename="delete_study__responses(is_preview=True)",
        description="Delete preview data for study",
    )
    APPROVE_REJECT_STUDY = _PermissionMetaStudiesApp(
        codename="edit_study__<APPROVAL>", description="Approve or reject study"
    )


UMBRELLA_LAB_PERMISSION_MAP = {
    study_perm: create_lab_version(study_perm) for study_perm in StudyPermission
}


class LabPermission(_PermissionMetaStudiesApp, Enum):
    CREATE_LAB_ASSOCIATED_STUDY = _PermissionMetaStudiesApp(
        codename="associate_lab__study", description="Associate a study with a lab"
    )
    MANAGE_LAB_RESEARCHERS = _PermissionMetaStudiesApp(
        codename="edit_lab__<GROUPS>", description="Manage researchers in a lab"
    )
    EDIT_LAB_METADATA = _PermissionMetaStudiesApp(
        codename="edit_lab__<DETAILS>", description="Edit the metadata for a lab"
    )
    EDIT_LAB_APPROVAL = _PermissionMetaStudiesApp(
        codename="edit_lab__approved_to_test",
        description="Edit whether a lab is approved to test",
    )
    READ_LAB_RESEARCHERS = _PermissionMetaStudiesApp(
        codename="read_lab__<GROUPS>",
        description="View the list of researchers in a lab",
    )

    READ_STUDY_DETAILS = UMBRELLA_LAB_PERMISSION_MAP[StudyPermission.READ_STUDY_DETAILS]

    WRITE_STUDY_DETAILS = UMBRELLA_LAB_PERMISSION_MAP[
        StudyPermission.WRITE_STUDY_DETAILS
    ]

    CHANGE_STUDY_STATUS = UMBRELLA_LAB_PERMISSION_MAP[
        StudyPermission.CHANGE_STUDY_STATUS
    ]

    MANAGE_STUDY_RESEARCHERS = UMBRELLA_LAB_PERMISSION_MAP[
        StudyPermission.MANAGE_STUDY_RESEARCHERS
    ]

    READ_STUDY_RESPONSE_DATA = UMBRELLA_LAB_PERMISSION_MAP[
        StudyPermission.READ_STUDY_RESPONSE_DATA
    ]

    READ_STUDY_PREVIEW_DATA = UMBRELLA_LAB_PERMISSION_MAP[
        StudyPermission.READ_STUDY_PREVIEW_DATA
    ]

    CODE_STUDY_CONSENT = UMBRELLA_LAB_PERMISSION_MAP[StudyPermission.CODE_STUDY_CONSENT]

    CODE_STUDY_PREVIEW_CONSENT = UMBRELLA_LAB_PERMISSION_MAP[
        StudyPermission.CODE_STUDY_PREVIEW_CONSENT
    ]

    CONTACT_STUDY_PARTICIPANTS = UMBRELLA_LAB_PERMISSION_MAP[
        StudyPermission.CONTACT_STUDY_PARTICIPANTS
    ]

    EDIT_STUDY_FEEDBACK = UMBRELLA_LAB_PERMISSION_MAP[
        StudyPermission.EDIT_STUDY_FEEDBACK
    ]

    CHANGE_STUDY_LAB = UMBRELLA_LAB_PERMISSION_MAP[StudyPermission.CHANGE_STUDY_LAB]

    DELETE_ALL_PREVIEW_DATA = UMBRELLA_LAB_PERMISSION_MAP[
        StudyPermission.DELETE_ALL_PREVIEW_DATA
    ]


class LabGroup(set, Enum):
    GUEST = {LabPermission.CREATE_LAB_ASSOCIATED_STUDY}
    READONLY = {LabPermission.READ_STUDY_DETAILS, LabPermission.READ_STUDY_PREVIEW_DATA}
    MEMBER = {
        LabPermission.CREATE_LAB_ASSOCIATED_STUDY,
        LabPermission.READ_LAB_RESEARCHERS,
        LabPermission.READ_STUDY_DETAILS,
        LabPermission.READ_STUDY_PREVIEW_DATA,
        LabPermission.CODE_STUDY_PREVIEW_CONSENT,
    }
    ADMIN = {
        # Umbrella permissions
        LabPermission.READ_STUDY_DETAILS,
        LabPermission.READ_STUDY_PREVIEW_DATA,
        LabPermission.CODE_STUDY_PREVIEW_CONSENT,
        LabPermission.DELETE_ALL_PREVIEW_DATA,
        LabPermission.WRITE_STUDY_DETAILS,
        LabPermission.CHANGE_STUDY_STATUS,
        LabPermission.MANAGE_STUDY_RESEARCHERS,
        # Lab-centric permissions
        LabPermission.CREATE_LAB_ASSOCIATED_STUDY,
        LabPermission.EDIT_LAB_METADATA,
        LabPermission.MANAGE_LAB_RESEARCHERS,
        LabPermission.READ_LAB_RESEARCHERS,
    }


class StudyGroup(set, Enum):
    PREVIEW = {
        StudyPermission.READ_STUDY_DETAILS,
        StudyPermission.READ_STUDY_PREVIEW_DATA,
        StudyPermission.CODE_STUDY_PREVIEW_CONSENT,
    }
    DESIGN = {
        StudyPermission.READ_STUDY_DETAILS,
        StudyPermission.READ_STUDY_PREVIEW_DATA,
        StudyPermission.CODE_STUDY_PREVIEW_CONSENT,
        StudyPermission.DELETE_ALL_PREVIEW_DATA,
        StudyPermission.WRITE_STUDY_DETAILS,
    }
    ANALYSIS = {
        StudyPermission.READ_STUDY_DETAILS,
        StudyPermission.READ_STUDY_PREVIEW_DATA,
        StudyPermission.CODE_STUDY_PREVIEW_CONSENT,
        StudyPermission.DELETE_ALL_PREVIEW_DATA,
        StudyPermission.READ_STUDY_RESPONSE_DATA,
    }
    SUBMISSION_PROCESSOR = {
        StudyPermission.READ_STUDY_DETAILS,
        StudyPermission.READ_STUDY_PREVIEW_DATA,
        StudyPermission.CODE_STUDY_PREVIEW_CONSENT,
        StudyPermission.DELETE_ALL_PREVIEW_DATA,
        StudyPermission.CHANGE_STUDY_STATUS,
        StudyPermission.CODE_STUDY_CONSENT,
        StudyPermission.EDIT_STUDY_FEEDBACK,
        StudyPermission.CONTACT_STUDY_PARTICIPANTS,
    }
    RESEARCHER = {
        StudyPermission.READ_STUDY_DETAILS,
        StudyPermission.READ_STUDY_PREVIEW_DATA,
        StudyPermission.CODE_STUDY_PREVIEW_CONSENT,
        StudyPermission.DELETE_ALL_PREVIEW_DATA,
        StudyPermission.CHANGE_STUDY_STATUS,
        StudyPermission.READ_STUDY_RESPONSE_DATA,
        StudyPermission.CODE_STUDY_CONSENT,
        StudyPermission.EDIT_STUDY_FEEDBACK,
        StudyPermission.CONTACT_STUDY_PARTICIPANTS,
    }
    MANAGER = {
        StudyPermission.READ_STUDY_DETAILS,
        StudyPermission.READ_STUDY_PREVIEW_DATA,
        StudyPermission.CODE_STUDY_PREVIEW_CONSENT,
        StudyPermission.DELETE_ALL_PREVIEW_DATA,
        StudyPermission.WRITE_STUDY_DETAILS,
        StudyPermission.CHANGE_STUDY_STATUS,
        StudyPermission.MANAGE_STUDY_RESEARCHERS,
    }
    ADMIN = {
        StudyPermission.READ_STUDY_DETAILS,
        StudyPermission.READ_STUDY_PREVIEW_DATA,
        StudyPermission.CODE_STUDY_PREVIEW_CONSENT,
        StudyPermission.DELETE_ALL_PREVIEW_DATA,
        StudyPermission.WRITE_STUDY_DETAILS,
        StudyPermission.EDIT_STUDY_FEEDBACK,
        StudyPermission.CHANGE_STUDY_STATUS,
        StudyPermission.MANAGE_STUDY_RESEARCHERS,
        StudyPermission.READ_STUDY_RESPONSE_DATA,
        StudyPermission.CODE_STUDY_CONSENT,
        StudyPermission.CONTACT_STUDY_PARTICIPANTS,
        StudyPermission.CHANGE_STUDY_LAB,
    }


class SiteAdminGroup(set, Enum):
    """
    Simple starting point/placeholder for site-wide groups. Because the current permissions are directly related
    to Study and Lab permissions, keep here for now; upon creating other site-level perms and groups, may
    transfer to accounts app.
    """

    LOOKIT_ADMIN = {
        StudyPermission.APPROVE_REJECT_STUDY,
        StudyPermission.CHANGE_STUDY_STATUS,
        LabPermission.EDIT_LAB_APPROVAL,
        LabPermission.EDIT_LAB_METADATA,
        LabPermission.READ_LAB_RESEARCHERS,
        LabPermission.MANAGE_LAB_RESEARCHERS,
    }
