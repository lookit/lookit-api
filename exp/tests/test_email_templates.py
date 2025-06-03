import uuid

from bs4 import BeautifulSoup
from django.template.loader import render_to_string
from django.test import TestCase, override_settings
from django_dynamic_fixture import G
from parameterized import parameterized

from accounts.models import User
from studies.models import Study, StudyType

fake_website = "https://fakeweb.site/"


@override_settings(BASE_URL=fake_website)
class EmailTemplatesTestCase(TestCase):
    def test_notify_researcher_of_lab_permissions_html_lab_url(self):
        context = {"lab_id": 4321}
        html = render_to_string(
            "emails/notify_researcher_of_lab_permissions.html", context
        )
        bs = BeautifulSoup(html, "html.parser")
        self.assertEqual(bs.a["href"], f"{fake_website}exp/labs/4321/")

    def test_notify_researcher_of_lab_permissions_txt_lab_url(self):
        context = {"lab_id": 4321}
        txt = render_to_string(
            "emails/notify_researcher_of_lab_permissions.txt", context
        )
        self.assertIn(f"Here is a link to this lab: {fake_website}exp/labs/4321/.", txt)

    def test_notify_researcher_of_study_permissions_html_study_url(self):
        context = {"study_id": 4321}
        html = render_to_string(
            "emails/notify_researcher_of_study_permissions.html", context
        )
        bs = BeautifulSoup(html, "html.parser")
        self.assertEqual(bs.a["href"], f"{fake_website}exp/studies/4321/")

    def test_notify_researcher_of_study_permissions_txt_study_url(self):
        context = {"study_id": 4321}
        txt = render_to_string(
            "emails/notify_researcher_of_study_permissions.txt", context
        )
        self.assertIn(
            f"Here is a link to start collaborating: {fake_website}exp/studies/4321/.",
            txt,
        )

    def test_base_html_email_prefs_unsubscribe_html_url(self):
        user = G(User, username="fake@email.com")
        context = {"username": user.username, "token": user.generate_token()}
        html = render_to_string("emails/base.html", context)
        bs = BeautifulSoup(html, "html.parser")
        links = list(bs.findAll("a"))

        # Double check that we didn't populate token with an empty value.
        self.assertTrue(context["token"])
        self.assertEqual(len(links), 3)
        self.assertEqual(links[0]["href"], f"{fake_website}account/email/")
        self.assertEqual(
            links[1]["href"],
            f"{fake_website}account/fake@email.com/{context['token']}/",
        )
        self.assertEqual(
            links[2]["href"],
            "mailto:childrenhelpingscience@gmail.com?subject=CHS Family Feedback or Question",
        )

    def test_base_html_email_prefs_unsubscribe_txt_url(self):
        user = G(User, username="fake@email.com")
        context = {"username": user.username, "token": user.generate_token()}
        txt = render_to_string("emails/base.txt", context)
        self.assertTrue(context["token"])
        self.assertIn(
            f"Unsubscribe from all CHS emails: {fake_website}account/fake@email.com/{context['token']}/\n",
            txt,
        )
        self.assertIn(
            f"Update your CHS email preferences here: {fake_website}account/email/\n",
            txt,
        )

    def test_notify_admins_of_lab_creation_html_url(self):
        context = {"lab_id": 4321}
        html = render_to_string("emails/notify_admins_of_lab_creation.html", context)
        bs = BeautifulSoup(html, "html.parser")
        self.assertEqual(bs.a["href"], f"{fake_website}exp/labs/4321/edit/")

    def test_notify_admins_of_lab_creation_txt_url(self):
        context = {"lab_id": 4321}
        txt = render_to_string("emails/notify_admins_of_lab_creation.txt", context)
        self.assertIn(
            f"You can approve the lab here: {fake_website}exp/labs/4321/edit/\n",
            txt,
        )

    @parameterized.expand(["submitted", "active", "paused", "deactivated"])
    def test_notify_admins_of_study_action_html_url(self, action):
        context = {"study_id": 4321, "action": action}
        html = render_to_string("emails/notify_admins_of_study_action.html", context)
        bs = BeautifulSoup(html, "html.parser")
        self.assertEqual(bs.a["href"], f"{fake_website}exp/studies/4321/")

    @parameterized.expand(["submitted", "active", "paused", "deactivated"])
    def test_notify_admins_of_study_action_txt_url(self, action):
        context = {"study_id": 4321, "action": action}
        txt = render_to_string("emails/notify_admins_of_study_action.txt", context)
        self.assertIn(f" {fake_website}exp/studies/4321/\n", txt)

    def test_notify_lab_admins_of_approval_html_url(self):
        context = {"lab_id": 4321}
        html = render_to_string("emails/notify_lab_admins_of_approval.html", context)
        bs = BeautifulSoup(html, "html.parser")
        self.assertEqual(bs.a["href"], f"{fake_website}exp/labs/4321/")

    def test_notify_lab_admins_of_approval_txt_url(self):
        context = {"lab_id": 4321}
        txt = render_to_string("emails/notify_lab_admins_of_approval.txt", context)
        self.assertIn(
            f"You can view your lab here: {fake_website}exp/labs/4321/\n", txt
        )

    def test_notify_admins_of_request_to_join_html_url(self):
        context = {"lab_pk": 4321}
        html = render_to_string(
            "emails/notify_lab_admins_of_request_to_join.html", context
        )
        bs = BeautifulSoup(html, "html.parser")
        self.assertEqual(bs.a["href"], f"{fake_website}exp/labs/4321/members/")

    def test_notify_admins_of_request_to_join_txt_url(self):
        context = {"lab_pk": 4321}
        txt = render_to_string(
            "emails/notify_lab_admins_of_request_to_join.txt", context
        )
        self.assertIn(
            f"You can approve the request and set their permissions here: {fake_website}exp/labs/4321/members/\n",
            txt,
        )

    def test_notify_researchers_of_approval_decision_html_url(self):
        context = {"study_id": 4321}
        html = render_to_string(
            "emails/notify_researchers_of_approval_decision.html", context
        )
        bs = BeautifulSoup(html, "html.parser")
        self.assertEqual(bs.a["href"], f"{fake_website}exp/studies/4321/")

    def test_notify_researchers_of_approval_decision_txt_url(self):
        context = {"study_id": 4321}
        txt = render_to_string(
            "emails/notify_researchers_of_approval_decision.txt", context
        )
        self.assertIn(
            f"Your study can be found here: {fake_website}exp/studies/4321/\n",
            txt,
        )

    def test_notify_researchers_of_build_failure_html_url(self):
        context = {"study_id": 4321}
        html = render_to_string(
            "emails/notify_researchers_of_build_failure.html", context
        )
        bs = BeautifulSoup(html, "html.parser")
        self.assertEqual(bs.a["href"], f"{fake_website}exp/studies/4321/")

    def test_notify_researchers_of_build_failure_txt_url(self):
        context = {"study_id": 4321, "study_name": "Some Study Name"}
        txt = render_to_string(
            "emails/notify_researchers_of_build_failure.txt", context
        )
        self.assertIn(
            f"The experiment runner for your study, Some Study Name ({fake_website}exp/studies/4321/),",
            txt,
        )

    def test_notify_researchers_of_deployment_html_url(self):
        context = {"study_uuid": uuid.uuid4(), "study_id": 4321}
        html = render_to_string("emails/notify_researchers_of_deployment.html", context)
        bs = BeautifulSoup(html, "html.parser")
        links = list(bs.findAll("a"))
        self.assertEqual(len(links), 3)
        self.assertEqual(links[0]["href"], f"{fake_website}exp/studies/4321/")
        self.assertEqual(
            links[1]["href"],
            f"{fake_website}exp/studies/{context['study_uuid']}/preview-detail/",
        )
        self.assertEqual(
            links[2]["href"],
            f"{fake_website}studies/{context['study_uuid']}/",
        )

    def test_notify_researchers_of_deployment_txt_url(self):
        context = {
            "study_uuid": uuid.uuid4(),
            "study_id": 4321,
            "study_name": "Some Study Name",
        }
        txt = render_to_string("emails/notify_researchers_of_deployment.txt", context)
        self.assertIn(
            f"An experiment runner has been built for Some Study Name ({fake_website}exp/studies/4321/).",
            txt,
        )
        self.assertIn(
            f"This study can now be previewed here: {fake_website}exp/studies/{context['study_uuid']}/preview-detail/",
            txt,
        )

    def test_study_announcement_html_url(self):
        study = G(Study, study_type=StudyType.get_ember_frame_player())
        user = G(User)
        context = {
            "study": study,
            "username": user.username,
            "token": user.generate_token(),
        }
        html = render_to_string("emails/study_announcement.html", context)
        bs = BeautifulSoup(html, "html.parser")
        links = list(bs.findAll("a"))

        # There are more links due to this template extending the base template
        self.assertEqual(len(links), 5)

        self.assertEqual(links[0]["href"], f"{fake_website}studies/{study.uuid}/")
        self.assertEqual(links[1]["href"], f"{fake_website}studies/{study.uuid}/")

    def test_study_announcement_txt_url(self):
        study = G(Study, study_type=StudyType.get_ember_frame_player())
        user = G(User)
        context = {
            "study": study,
            "username": user.username,
            "token": user.generate_token(),
        }
        txt = render_to_string("emails/study_announcement.txt", context)
        self.assertIn(
            f'by going to "{study.name}" ({fake_website}studies/{study.uuid}/).',
            txt,
        )
