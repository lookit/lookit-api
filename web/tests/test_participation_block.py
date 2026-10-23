from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django_dynamic_fixture import G
from parameterized import parameterized

from accounts.models import Child, DemographicData, User
from studies.models import Lab, Response, Study, StudyType
from web import geoip
from web.models import BlockRule, ParticipationBlockRecord

BLOCKED_IP = "203.0.113.7"
OTHER_IP = "198.51.100.1"
# Marks the participate button that only spins and reloads the page.
BLOCKED_BUTTON = "data-participation-bkd"


class ParticipationBlockTestCase(TestCase):
    """Blocked participants who are logged in are logged, so each test that
    blocks one checks for that, which also keeps the log out of the test output.
    That includes assertRedirects, which fetches the study detail page from the
    same IP address.
    """

    def setUp(self):
        # Rolling back a test's rules doesn't clear the cache.
        BlockRule.clear_cache()
        self.addCleanup(BlockRule.clear_cache)
        # Instead of the GeoIP databases: visitors are in an unknown country, on
        # an unknown network, unless a test sets self.country's or self.asn's
        # return_value.
        self.country = self.enterContext(patch("web.geoip.country", return_value=None))
        self.asn = self.enterContext(patch("web.geoip.asn", return_value=None))
        self.rule = BlockRule.objects.create(value=BLOCKED_IP)

        self.user = G(User, is_active=True)
        self.child = G(Child, user=self.user, deleted=False)
        G(DemographicData, user=self.user)
        self.client.force_login(self.user)

    def make_study(self, study_type):
        study = G(
            Study,
            lab=G(Lab),
            study_type=study_type,
            # What an external study's page needs.
            metadata={"url": "", "scheduled": False},
            public=True,
            image=SimpleUploadedFile(
                "fake_image.png", b"fake-stuff", content_type="image/png"
            ),
        )
        study.state = "active"
        study.save()
        return study

    def study_detail_url(self, study_type=None):
        study = self.make_study(study_type or StudyType.get_jspsych())
        return reverse("web:study-detail", kwargs={"uuid": study.uuid})

    def test_site_is_usable(self):
        response = self.client.get(reverse("web:home"), HTTP_X_REAL_IP=BLOCKED_IP)
        self.assertEqual(response.status_code, 200)

    def assertDecoyButton(self, response):
        """The participate button is there, but doesn't submit the form."""
        self.assertContains(response, 'id="participate-button"', count=1)
        self.assertContains(response, BLOCKED_BUTTON)

    def test_study_detail_participate_button_does_not_submit(self):
        url = self.study_detail_url()

        with self.assertLogs("web.middleware", level="INFO"):
            response = self.client.get(url, HTTP_X_REAL_IP=BLOCKED_IP)
        self.assertEqual(response.status_code, 200)
        self.assertDecoyButton(response)

        with self.assertNoLogs("web.middleware", level="INFO"):
            response = self.client.get(url, HTTP_X_REAL_IP=OTHER_IP)
        self.assertContains(response, 'id="participate-button"')
        self.assertNotContains(response, BLOCKED_BUTTON)

    def test_logged_out_visitor_sees_log_in_buttons(self):
        url = self.study_detail_url()

        # There's no participant to log.
        with self.assertNoLogs("web.middleware", level="INFO"):
            response = self.client_class().get(url, HTTP_X_REAL_IP=BLOCKED_IP)
        self.assertContains(response, "Log in to participate")

    def test_country_rule(self):
        self.country.return_value = "RU"
        BlockRule.objects.create(kind=BlockRule.Kind.COUNTRY, value="RU")
        url = self.study_detail_url()

        with self.assertLogs("web.middleware", level="INFO"):
            response = self.client.get(url, HTTP_X_REAL_IP=OTHER_IP)
        self.assertDecoyButton(response)
        self.country.assert_called_with(OTHER_IP)

    def test_network_owner_rule(self):
        # Like the VPN rules that manage.py load_vpn_asn_rules adds.
        self.asn.return_value = geoip.ASN(9009, "M247 Europe SRL")
        rule = BlockRule.objects.create(kind=BlockRule.Kind.ASN, value="AS9009")
        url = self.study_detail_url()

        with self.assertLogs("web.middleware", level="INFO") as logs:
            response = self.client.get(url, HTTP_X_REAL_IP=OTHER_IP)
        self.assertDecoyButton(response)
        self.asn.assert_called_with(OTHER_IP)
        self.assertIn(
            f"Block rule {rule.pk} (AS9009) stopped user {self.user.pk}",
            logs.output[0],
        )

    @parameterized.expand(
        [
            (
                "known",
                "GB",
                geoip.ASN(9009, "M247 Europe SRL"),
                "They're in GB, on AS9009 (M247 Europe SRL), in IP range 203.0.113.0/24.",
            ),
            (
                "unknown",
                None,
                None,
                "They're in an unknown country, on an unknown network, in IP range "
                "203.0.113.0/24.",
            ),
            (
                "unnamed network",
                "GB",
                geoip.ASN(64496, ""),
                "They're in GB, on AS64496, in IP range 203.0.113.0/24.",
            ),
        ]
    )
    def test_logs_which_rule_stopped_participant(self, _, country, asn, where):
        self.country.return_value = country
        self.asn.return_value = asn
        url = self.study_detail_url()

        with self.assertLogs("web.middleware", level="INFO") as logs:
            self.client.get(url, HTTP_X_REAL_IP=BLOCKED_IP)

        # Without their IP address, which an IP address rule's value can be, but
        # with the range it's in.
        self.assertEqual(
            logs.output,
            [
                f"INFO:web.middleware:Block rule {self.rule.pk} (IP address or range) "
                f"stopped user {self.user.pk} participating in studies, at GET {url}. "
                f"{where}"
            ],
        )

    def test_records_which_rule_stopped_participant(self):
        self.country.return_value = "GB"
        self.asn.return_value = geoip.ASN(9009, "M247 Europe SRL")
        url = self.study_detail_url()

        with self.assertLogs("web.middleware", level="INFO"):
            self.client.get(url, HTTP_X_REAL_IP=BLOCKED_IP)
            self.client.get(url, HTTP_X_REAL_IP=BLOCKED_IP)

        record = ParticipationBlockRecord.objects.get()
        self.assertEqual(
            (
                record.user,
                record.rule,
                record.times_blocked,
                record.network,
                record.country,
                record.asn,
                record.asn_organization,
            ),
            (self.user, self.rule, 2, "203.0.113.0/24", "GB", 9009, "M247 Europe SRL"),
        )

    def test_logged_out_visitor_not_recorded(self):
        with self.assertNoLogs("web.middleware", level="INFO"):
            self.client_class().get(self.study_detail_url(), HTTP_X_REAL_IP=BLOCKED_IP)
        self.assertFalse(ParticipationBlockRecord.objects.exists())

    def test_recording_fails_open(self):
        url = self.study_detail_url()
        with (
            patch.object(
                ParticipationBlockRecord, "record", side_effect=TypeError("oops")
            ),
            self.assertLogs("web.middleware", level="INFO") as logs,
        ):
            response = self.client.get(url, HTTP_X_REAL_IP=BLOCKED_IP)
        self.assertDecoyButton(response)
        self.assertIn("Could not record a participation block", logs.output[1])

    def test_study_detail_post_does_not_start_external_study(self):
        url = self.study_detail_url(StudyType.get_external())

        with self.assertLogs("web.middleware", level="INFO") as logs:
            response = self.client.post(
                url, {"child_id": self.child.uuid}, HTTP_X_REAL_IP=BLOCKED_IP
            )
            self.assertRedirects(response, url)
        self.assertIn(f"at POST {url}.", logs.output[0])
        self.assertFalse(Response.objects.exists())

    def test_jspsych_experiment_redirects_to_study_detail(self):
        study = self.make_study(StudyType.get_jspsych())
        with self.assertLogs("web.middleware", level="INFO"):
            response = self.client.get(
                reverse(
                    "web:jspsych-experiment",
                    kwargs={"uuid": study.uuid, "child_id": self.child.uuid},
                ),
                HTTP_X_REAL_IP=BLOCKED_IP,
            )
            self.assertRedirects(
                response, reverse("web:study-detail", kwargs={"uuid": study.uuid})
            )
        self.assertFalse(Response.objects.filter(study=study).exists())

    def test_experiment_proxy_redirects_to_study_detail(self):
        study = self.make_study(StudyType.get_ember_frame_player())
        with self.assertLogs("web.middleware", level="INFO"):
            response = self.client.get(
                reverse(
                    "web:experiment-proxy",
                    kwargs={"uuid": study.uuid, "child_id": self.child.uuid},
                ),
                HTTP_X_REAL_IP=BLOCKED_IP,
            )
            self.assertRedirects(
                response, reverse("web:study-detail", kwargs={"uuid": study.uuid})
            )

    @override_settings(DEBUG=True, ENVIRONMENT="develop")
    def test_experiment_proxy_redirects_to_study_detail_locally(self):
        # Locally, the view redirects to the Ember server instead of proxying.
        study = self.make_study(StudyType.get_ember_frame_player())
        with self.assertLogs("web.middleware", level="INFO"):
            response = self.client.get(
                reverse(
                    "web:experiment-proxy",
                    kwargs={"uuid": study.uuid, "child_id": self.child.uuid},
                ),
                HTTP_X_REAL_IP=BLOCKED_IP,
            )
            self.assertRedirects(
                response, reverse("web:study-detail", kwargs={"uuid": study.uuid})
            )

    @override_settings(BLOCK_RULES_REPORT_ONLY=True)
    def test_report_only_logs_and_records_without_blocking(self):
        url = self.study_detail_url()

        with self.assertLogs("web.middleware", level="INFO") as logs:
            response = self.client.get(url, HTTP_X_REAL_IP=BLOCKED_IP)
        self.assertContains(response, 'id="participate-button"')
        self.assertNotContains(response, BLOCKED_BUTTON)
        self.assertIn(
            f"Block rule {self.rule.pk} (IP address or range) would have stopped "
            f"(report only) user {self.user.pk} participating in studies",
            logs.output[0],
        )
        record = ParticipationBlockRecord.objects.get()
        self.assertEqual((record.user, record.rule), (self.user, self.rule))

    @override_settings(BLOCK_RULES_REPORT_ONLY=True)
    def test_report_only_lets_participant_start_study(self):
        study = self.make_study(StudyType.get_jspsych())
        with self.assertLogs("web.middleware", level="INFO"):
            response = self.client.get(
                reverse(
                    "web:jspsych-experiment",
                    kwargs={"uuid": study.uuid, "child_id": self.child.uuid},
                ),
                HTTP_X_REAL_IP=BLOCKED_IP,
            )
        # Not redirected back to the study detail page.
        self.assertEqual(response.status_code, 200)
