from django.utils.text import slugify

def build_group_name(org_name, group):
    """Returns group name in the form of <ORGNAME>_ORG_<GROUP>"""
    return f'{slugify({org_name})}_ORG_{group}'.upper()
