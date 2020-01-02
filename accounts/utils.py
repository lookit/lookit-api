from django.utils.text import slugify
import hashlib
import base64


def build_org_group_name(org_name, group):
    """
    Returns org group name in the form of <ORGNAME>_ORG_<GROUP>
    """
    return f"{slugify({org_name})}_ORG_{group}".upper()


def build_study_group_name(org_name, study_name, study_pk, group):
    """
    Returns study group name in the form of <ORGNAME>_<TRUNCATED_STUDY_NAME>_<STUDY_PK>_STUDY_<GROUP>

    Study portion of group name is truncated to 20 characters
    """
    return f"{slugify({org_name})}_{slugify({study_name[:20]})}_{study_pk}_STUDY_{group}".upper()


def hash_id(id1, id2, salt, length=5):
    concat = bytes([a ^ b ^ c for (a, b, c) in zip(id1.bytes, id2.bytes, salt.bytes)])
    hashed = base64.b32encode(hashlib.sha256(concat).digest()).decode("utf-8")
    hashed = hashed.translate("".maketrans("10IO", "abcd"))
    return hashed[:length]
