import base64
import hashlib

from django.utils.text import slugify

from studies.models import Response


def build_org_group_name(org_name, group):
    """
    Returns org group name in the form of <ORGNAME>_ORG_<GROUP>.

    Unused - keep for now only for future migration to help remove these groups.
    (Only org name     was MIT.)
    """
    return f"{slugify({org_name})}_ORG_{group}".upper()


def build_study_group_name(org_name, study_name, study_pk, group):
    """
    Returns study group name in the form of <ORGNAME>_<TRUNCATED_STUDY_NAME>_<STUDY_PK>_STUDY_<GROUP>

    Study portion of group name is truncated to 20 characters

    Unused - keep for now only for future migration to help remove these groups.
    """
    return f"{slugify({org_name})}_{slugify({study_name[:20]})}_{study_pk}_STUDY_{group}".upper()


def hash_id(id1, id2, salt, length=6):
    concat = bytes([a ^ b ^ c for (a, b, c) in zip(id1.bytes, id2.bytes, salt.bytes)])
    hashed = base64.b32encode(hashlib.sha256(concat).digest()).decode("utf-8")
    hashed = hashed.translate("".maketrans("10IO", "abcd"))
    return hashed[:length]


def hash_child_id(resp):
    return hash_id(
        resp["child__uuid"],
        resp["study__uuid"],
        resp["study__salt"],
        resp["study__hash_digits"],
    )


def hash_child_id_from_model(resp: Response):
    return hash_id(
        resp.child.uuid, resp.study.uuid, resp.study.salt, resp.study.hash_digits
    )


def hash_participant_id(resp):
    return hash_id(
        resp["child__user__uuid"],
        resp["study__uuid"],
        resp["study__salt"],
        resp["study__hash_digits"],
    )


def hash_demographic_id(resp):
    return hash_id(
        resp["demographic_snapshot__uuid"],
        resp["study__uuid"],
        resp["study__salt"],
        resp["study__hash_digits"],
    )
