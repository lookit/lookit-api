from django.utils.text import slugify

def build_org_group_name(org_name, group):
    """Returns org group name in the form of <ORGNAME>_ORG_<GROUP>"""
    return f'{slugify({org_name})}_ORG_{group}'.upper()
