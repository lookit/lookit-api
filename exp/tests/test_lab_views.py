from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django_dynamic_fixture import G
from guardian.shortcuts import assign_perm

from accounts.backends import TWO_FACTOR_AUTH_SESSION_KEY
from accounts.models import User
from studies.models import Lab, Study, StudyType
from studies.permissions import LabPermission


class Force2FAClient(Client):
    """For convenience, let's just pretend everyone is two-factor auth'd."""

    @property
    def session(self):
        _session = super().session
        _session[TWO_FACTOR_AUTH_SESSION_KEY] = True
        return _session


# run celery .delay() tasks right away and propagate errors.
# Ideally to test celery tasks we would mock per
# https://docs.celeryproject.org/en/stable/userguide/testing.html
# but for these views the celery tasks are relatively unimportant and
# we're happy just checking there aren't errors when emails are sent.
@override_settings(CELERY_TASK_ALWAYS_EAGER=True)
@override_settings(CELERY_TASK_EAGER_PROPAGATES=True)
class LabViewsTestCase(TestCase):
    def setUp(self):
        self.client = Force2FAClient()

        self.lab = G(Lab, name="ECCL", institution="MIT", approved_to_test=False)
        self.lab2 = G(Lab, name="Second lab")
        self.researcher = G(
            User, is_active=True, is_researcher=True, given_name="Alice"
        )
        self.researcher_outside_lab = G(
            User, is_active=True, is_researcher=True, given_name="Bobbington"
        )
        self.researcher_in_lab = G(
            User, is_active=True, is_researcher=True, given_name="Candice"
        )
        self.lab.researchers.add(self.researcher)
        self.lab.researchers.add(self.researcher_in_lab)
        self.lab.member_group.user_set.add(self.researcher_in_lab)
        self.lab.save()

        self.study_type = G(StudyType, name="default", id=1)
        self.study = G(
            Study, creator=self.researcher, study_type=self.study_type, lab=self.lab
        )
        self.study.researcher_group.user_set.add(self.researcher_in_lab)

        self.superuser = G(User, is_active=True, is_researcher=True, is_superuser=True)
        self.participant = G(User, is_active=True)

        self.create_lab_url = reverse("exp:lab-create")
        self.lab_detail_url = reverse("exp:lab-detail", kwargs={"pk": self.lab.pk})
        self.lab_members_url = reverse("exp:lab-members", kwargs={"pk": self.lab.pk})
        self.lab_list_url = reverse("exp:lab-list")
        self.lab2_request_url = reverse("exp:lab-request", kwargs={"pk": self.lab2.pk})
        self.lab_update_url = reverse("exp:lab-edit", kwargs={"pk": self.lab.pk})

    # Create lab view: can get as researcher
    def testCanGetCreateLabViewAsResearcher(self):
        self.client.force_login(self.researcher)
        page = self.client.get(self.create_lab_url)
        self.assertEqual(
            page.status_code, 200, "Unable to get create lab view as researcher"
        )
        self.assertTemplateUsed(
            page,
            "studies/lab_create.html",
            "Incorrect template used for displaying create lab form",
        )

    # Create lab view: can create new lab as researcher
    def testCanCreateNewLabAsResearcher(self):
        self.client.force_login(self.researcher)
        post_data = {
            "name": "New lab",
            "principal_investigator_name": "Jane Smith",
            "institution": "MIT",
            "contact_email": "abc@def.org",
            "contact_phone": "(123) 456-7890",
            "lab_website": "https://mit.edu",
            "description": "ABCDEFG",
            "irb_contact_info": "how to reach the IRB",
        }
        page = self.client.post(self.create_lab_url, post_data)
        self.assertEqual(page.status_code, 302, "Unable to create lab as researcher")

    # Create lab view: cannot get as participant
    def testCanGetCreateLabViewAsParticipant(self):
        self.client.force_login(self.participant)
        page = self.client.get(self.create_lab_url)
        self.assertEqual(
            page.status_code, 403, "Participant is able to create a new lab!"
        )

    # Lab detail view: can see as researcher
    def testCanGetLabDetailViewAsResearcher(self):
        self.client.force_login(self.researcher)
        page = self.client.get(self.lab_detail_url)
        self.assertEqual(
            page.status_code, 200, "Unable to get lab detail view as researcher"
        )
        self.assertTemplateUsed(
            page,
            "studies/lab_detail.html",
            "Incorrect template used for displaying lab detail page",
        )

    # Lab detail view: cannot see as participant
    def testCanGetLabDetailViewAsParticipant(self):
        self.client.force_login(self.participant)
        page = self.client.get(self.lab_detail_url)
        self.assertEqual(
            page.status_code, 403, "Participant is able to view exp lab detail page!"
        )

    # Lab members view: cannot see as researcher not in lab
    def testCannotGetLabMembersViewAsUnaffiliatedResearcher(self):
        self.client.force_login(self.researcher_outside_lab)
        page = self.client.get(self.lab_members_url)
        self.assertEqual(
            page.status_code, 403, "Unaffiliated researcher is able to view lab members"
        )

    # Lab members view: can see as researcher in lab.
    def testCanGetLabMembersViewAsLabResearcher(self):
        self.client.force_login(self.researcher)
        page = self.client.get(self.lab_members_url)
        self.assertEqual(
            page.status_code, 200, "Unable to get lab members view as lab researcher"
        )
        self.assertTemplateUsed(
            page,
            "studies/lab_member_list.html",
            "Incorrect template used for displaying lab member page",
        )
        # note - can use page.context_data too!
        self.assertIn("Alice", page.rendered_content)
        self.assertIn("Candice", page.rendered_content)
        self.assertNotIn("Bobbington", page.rendered_content)

    # Lab members view: cannot post as researcher in lab w/o manage perms
    def testPostLabMembersViewIncorrectPerms(self):
        self.client.force_login(self.researcher)
        post_data = {
            "user_action": "make_member",
            "user_id": self.researcher_outside_lab.pk,
        }
        page = self.client.post(self.lab_members_url, post_data)
        self.assertEqual(
            page.status_code,
            403,
            "Researcher able to add new lab member without permissions",
        )

    # Lab members view: can add new researcher w/ appropriate perms
    def testAddNewLabMemberWithCorrectPerms(self):
        self.client.force_login(self.researcher)
        assign_perm(
            LabPermission.MANAGE_LAB_RESEARCHERS.codename, self.researcher, self.lab
        )
        post_data = {
            "user_action": "make_guest",
            "user_id": self.researcher_outside_lab.pk,
        }
        page = self.client.post(self.lab_members_url, post_data)
        self.assertEqual(
            page.status_code,
            302,
            "Researcher unable to add new lab member despite correct permissions",
        )
        self.assertRedirects(page, self.lab_members_url)
        self.assertIn(
            self.lab,
            self.researcher_outside_lab.labs.all(),
            "Researcher not successfully added to lab",
        )
        self.assertIn(self.researcher_outside_lab, self.lab.guest_group.user_set.all())

    # Lab members view: can remove researcher w/ appropriate perms
    def testRemoveLabMemberWithCorrectPerms(self):
        self.client.force_login(self.researcher)
        assign_perm(
            LabPermission.MANAGE_LAB_RESEARCHERS.codename, self.researcher, self.lab
        )
        post_data = {
            "user_action": "remove_researcher",
            "user_id": self.researcher_in_lab.pk,
        }
        page = self.client.post(self.lab_members_url, post_data)
        self.assertEqual(
            page.status_code,
            302,
            "Researcher unable to remove lab member despite correct permissions",
        )
        self.assertRedirects(page, self.lab_members_url)
        self.assertNotIn(self.lab, self.researcher_in_lab.labs.all())
        self.assertNotIn(
            self.researcher_in_lab,
            self.lab.member_group.user_set.all(),
            "Researcher removed from lab but not from associated member group",
        )
        self.assertNotIn(
            self.researcher_in_lab,
            self.study.researcher_group.user_set.all(),
            "Researcher removed from lab but not from associated study group",
        )

    # Lab list view: can see as researcher
    def testCanGetLabListViewAsResearcher(self):
        self.client.force_login(self.researcher)
        page = self.client.get(self.lab_list_url)
        self.assertEqual(
            page.status_code, 200, "Unable to get lab list view as researcher"
        )
        self.assertTemplateUsed(
            page,
            "studies/lab_list.html",
            "Incorrect template used for displaying lab list page",
        )

    # Lab list view: cannot see as participant
    def testCanGetLabListViewAsParticipant(self):
        self.client.force_login(self.participant)
        page = self.client.get(self.lab_list_url)
        self.assertEqual(
            page.status_code, 403, "Participant is able to view exp lab list page!"
        )

    # Lab update view: cannot get as researcher w/o edit perms
    def testGetLabUpdateViewIncorrectPerms(self):
        assign_perm(
            LabPermission.MANAGE_LAB_RESEARCHERS.codename, self.researcher, self.lab
        )
        self.client.force_login(self.researcher)
        page = self.client.get(self.lab_update_url)
        self.assertEqual(
            page.status_code,
            403,
            "Researcher able to access lab update view without permissions",
        )

    # Lab update view: can get as researcher w/ edit perms
    def testGetLabUpdateViewCorrectPerms(self):
        assign_perm(LabPermission.EDIT_LAB_METADATA.codename, self.researcher, self.lab)
        self.client.force_login(self.researcher)
        page = self.client.get(self.lab_update_url)
        self.assertEqual(
            page.status_code,
            200,
            "Researcher not able to access lab update view despite permissions",
        )

    # Lab update view: cannot post as researcher w/o edit perms
    def testPostLabUpdateViewIncorrectPerms(self):
        assign_perm(
            LabPermission.MANAGE_LAB_RESEARCHERS.codename, self.researcher, self.lab
        )
        self.client.force_login(self.researcher)
        post_data = {
            "name": "New lab",
            "principal_investigator_name": "Jane Smith",
            "institution": "New institution",
            "contact_email": "abc@def.org",
            "contact_phone": "(123) 456-7890",
            "lab_website": "https://mit.edu",
            "description": "ABCDEFG",
            "irb_contact_info": "how to reach the IRB",
        }
        page = self.client.post(self.lab_update_url, post_data)
        self.assertEqual(
            page.status_code,
            403,
            "Researcher able to edit lab metadata without permissions",
        )
        updated_lab = Lab.objects.get(pk=self.lab.pk)
        self.assertEqual(updated_lab.institution, "MIT")

    # Lab update view: can post as researcher w/ edit perms
    def testPostLabUpdateViewCorrectPerms(self):
        assign_perm(LabPermission.EDIT_LAB_METADATA.codename, self.researcher, self.lab)
        self.client.force_login(self.researcher)
        post_data = {
            "name": "New lab",
            "principal_investigator_name": "Jane Smith",
            "institution": "New institution",
            "contact_email": "abc@def.org",
            "contact_phone": "(123) 456-7890",
            "lab_website": "https://mit.edu",
            "description": "ABCDEFG",
            "irb_contact_info": "how to reach the IRB",
        }
        page = self.client.post(self.lab_update_url, post_data)
        self.assertEqual(
            page.status_code,
            302,
            "Researcher unable to edit lab metadata despite permissions",
        )
        updated_lab = Lab.objects.get(pk=self.lab.pk)
        self.assertEqual(updated_lab.institution, "New institution")

    # Lab update view: cannot update approved_to_test
    def testPostLabUpdateViewEditApproval(self):
        assign_perm(LabPermission.EDIT_LAB_METADATA.codename, self.researcher, self.lab)
        self.client.force_login(self.researcher)
        post_data = {
            "name": "New lab",
            "principal_investigator_name": "Jane Smith",
            "institution": "New institution",
            "contact_email": "abc@def.org",
            "contact_phone": "(123) 456-7890",
            "lab_website": "https://mit.edu",
            "description": "ABCDEFG",
            "irb_contact_info": "how to reach the IRB",
            "approved_to_test": True,
        }
        page = self.client.post(self.lab_update_url, post_data)
        updated_lab = Lab.objects.get(pk=self.lab.pk)
        self.assertFalse(
            updated_lab.approved_to_test,
            "Researcher approved lab to test without permission",
        )

    # Lab update view: can update approved_to_test as admin
    def testPostLabUpdateViewEditApprovalAsAdmin(self):
        assign_perm(LabPermission.EDIT_LAB_APPROVAL.prefixed_codename, self.researcher)
        assign_perm(LabPermission.EDIT_LAB_METADATA.prefixed_codename, self.researcher)
        self.client.force_login(self.researcher)
        post_data = {
            "name": "New lab",
            "principal_investigator_name": "Jane Smith",
            "institution": "New institution",
            "contact_email": "abc@def.org",
            "contact_phone": "(123) 456-7890",
            "lab_website": "https://mit.edu",
            "description": "ABCDEFG",
            "irb_contact_info": "how to reach the IRB",
            "approved_to_test": True,
        }
        page = self.client.post(self.lab_update_url, post_data)
        updated_lab = Lab.objects.get(pk=self.lab.pk)
        self.assertEqual(page.status_code, 302)
        self.assertTrue(
            updated_lab.approved_to_test,
            "Researcher could not approve lab to test despite permission",
        )

    # Lab membership request: can make as researcher
    def testRequestLabMembershipAsResearcher(self):
        self.client.force_login(self.researcher)
        page = self.client.post(self.lab2_request_url, {})
        self.assertEqual(
            page.status_code, 302, "Unable to request lab membership as researcher"
        )
        self.assertIn(self.researcher, self.lab2.requested_researchers.all())
        self.assertNotIn(self.researcher, self.lab2.researchers.all())

    # Lab membership request: cannot make as participant
    def testRequestLabMembershipAsParticipant(self):
        self.client.force_login(self.participant)
        page = self.client.post(self.lab2_request_url, {})
        self.assertEqual(
            page.status_code, 403, "Participant is able to request lab membership!"
        )
