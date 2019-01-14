from django.utils.text import slugify


def build_org_group_name(org_name, group):
    '''
    Returns org group name in the form of <ORGNAME>_ORG_<GROUP>
    '''
    return f'{slugify({org_name})}_ORG_{group}'.upper()


def build_study_group_name(org_name, study_name, study_pk, group):
    '''
    Returns study group name in the form of <ORGNAME>_<TRUNCATED_STUDY_NAME>_<STUDY_PK>_STUDY_<GROUP>

    Study portion of group name is truncated to 20 characters
    '''
    return f'{slugify({org_name})}_{slugify({study_name[:20]})}_{study_pk}_STUDY_{group}'.upper()
