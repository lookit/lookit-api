from django.contrib.auth.models import Group
from django.test import TestCase
from django.utils.text import slugify

from accounts.models import Organization, User
from guardian.shortcuts import get_perms
from studies.models import Study


class StudyPermissionsTestCase(TestCase):
    org_read_perms = [
        'can_view', 'can_view_permissions', 'can_view_demographics',
        'can_view_responses', 'can_view_video_responses'
    ]

    study_admin_perms = [
        'can_deactivate', 'can_resume', 'can_pause',
        'can_create', 'can_view_permissions', 'can_activate', 'can_retract',
        'can_view', 'can_edit_permissions', 'can_edit', 'can_remove',
        'can_view_responses', 'can_view_video_responses', 'can_resubmit',
        'can_submit', 'can_view_demographics'
    ]
    
    org_admin_perms = study_admin_perms + ['can_approve']

    study_read_perms = [
        'can_view'
    ]

    def setUp(self):
        org = Organization.objects.create(
            name='Test Organization',
            url='https://test.org'
        )
        study = Study.objects.create(
            name='Test Study',
            organization=org
        )

    def generate_group_names(self, org, study):
        group_names = []

        study_slug = slugify(study.name)
        org_slug = slugify(org.name)

        for group in ['read', 'admin']:
            group_names.append(f'{org_slug}_ORG_{group}'.upper())
            group_names.append(f'{org_slug}_{study_slug}_STUDY_{group}'.upper())

        return group_names

    def test_groups_created(self):
        '''
        Confirm that correct permissions are added upon study create.
        '''
        org = Organization.objects.first()
        study = Study.objects.first()

        group_names = self.generate_group_names(org, study)
        groups = Group.objects.filter(name__in=group_names)
        assert set(group_names) == set([g.name for g in groups])

    def test_perms_correct(self):
        org = Organization.objects.first()
        study = Study.objects.first()
        groups = Group.objects.all()
        for group in groups:
            perms = get_perms(group, study)
            if group.name == 'TEST-ORGANIZATION_ORG_READ':
                assert sorted(self.org_read_perms) == sorted(perms)
            if group.name == 'TEST-ORGANIZATION_ORG_ADMIN':
                assert sorted(self.org_admin_perms) == sorted(perms)
            if group.name == 'TEST-ORGANIZATION_TEST-STUDY_STUDY_ADMIN':
                assert sorted(self.study_admin_perms) == sorted(perms)
            if group.name == 'TEST-ORGANIZATION_TEST-STUDY_STUDY_READ':
                assert self.study_read_perms == perms
