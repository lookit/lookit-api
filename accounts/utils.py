from django.utils.text import slugify
from django.contrib import messages

from guardian.shortcuts import get_perms


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

# Dictionary with the states for the study and tooltip text for providing additional information
status_tooltip_text = {
    'created': 'Study has not been submitted for approval',
    'active': 'Study is collecting data',
    'submitted': 'Study is awaiting approval',
    'draft': 'Study has not been submitted for approval',
    'approved': 'Study is approved but not started',
    'rejected': 'Study has been rejected. Please edit before resubmitting.',
    'retracted': 'Study has been withdrawn',
    'paused': 'Study is not collecting data',
    'deactivated': 'Study is not collecting data',
    'archived': 'Study has been archived and removed from search.',
    'previewing': 'Study is being built and deployed to Google Cloud Storage for previewing.',
    'deploying': 'Study is being built and deployed to Google Cloud Storage'
}
