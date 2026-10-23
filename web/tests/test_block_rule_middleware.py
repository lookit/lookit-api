from unittest.mock import patch

from django.db import ProgrammingError
from django.http import HttpResponse
from django.test import RequestFactory, SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from parameterized import parameterized

from web.middleware import BlockRuleMiddleware, get_client_ip, participation_blocked
from web.models import BlockRule


class GetClientIPTestCase(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def test_uses_x_real_ip(self):
        request = self.factory.get(
            "/", HTTP_X_REAL_IP="203.0.113.7", REMOTE_ADDR="10.0.0.5"
        )
        self.assertEqual(get_client_ip(request), "203.0.113.7")

    def test_ignores_x_forwarded_for(self):
        request = self.factory.get(
            "/", HTTP_X_FORWARDED_FOR="198.51.100.1", REMOTE_ADDR="10.0.0.5"
        )
        self.assertEqual(get_client_ip(request), "10.0.0.5")

    def test_falls_back_to_remote_addr(self):
        request = self.factory.get("/", REMOTE_ADDR="10.0.0.5")
        self.assertEqual(get_client_ip(request), "10.0.0.5")

    def test_blank_header_falls_back_to_remote_addr(self):
        request = self.factory.get("/", HTTP_X_REAL_IP="  ", REMOTE_ADDR="10.0.0.5")
        self.assertEqual(get_client_ip(request), "10.0.0.5")

    @override_settings(CLIENT_IP_HEADER="HTTP_CF_CONNECTING_IP")
    def test_header_is_configurable(self):
        request = self.factory.get(
            "/", HTTP_CF_CONNECTING_IP="203.0.113.7", HTTP_X_REAL_IP="198.51.100.1"
        )
        self.assertEqual(get_client_ip(request), "203.0.113.7")


class BlockRuleMiddlewareTestCase(TestCase):
    def setUp(self):
        # Rolling back a test's rules doesn't clear the cache.
        BlockRule.clear_cache()
        self.addCleanup(BlockRule.clear_cache)
        self.factory = RequestFactory()
        self.middleware = BlockRuleMiddleware(lambda request: HttpResponse("ok"))
        BlockRule.objects.create(value="203.0.113.0/24", block_entire_site=True)

    def get(self, ip, **extra):
        return self.middleware(self.factory.get("/", HTTP_X_REAL_IP=ip, **extra))

    def test_blocked_ip_gets_block_page(self):
        response = self.get("203.0.113.7")
        self.assertContains(response, "Access blocked", status_code=403)

    def test_other_ip_passes_through(self):
        response = self.get("198.51.100.1")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"ok")

    def test_participation_only_rule_passes_through(self):
        BlockRule.objects.create(value="198.51.100.1")
        self.assertEqual(self.get("198.51.100.1").status_code, 200)

    def test_spoofed_x_forwarded_for_does_not_unblock(self):
        response = self.get("203.0.113.7", HTTP_X_FORWARDED_FOR="198.51.100.1")
        self.assertEqual(response.status_code, 403)

    @patch("web.geoip.country", return_value="RU")
    def test_country_rule(self, country):
        BlockRule.objects.create(
            kind=BlockRule.Kind.COUNTRY, value="RU", block_entire_site=True
        )
        self.assertEqual(self.get("198.51.100.1").status_code, 403)
        country.assert_called_once_with("198.51.100.1")

    @parameterized.expand(
        [
            ("database error", ProgrammingError("no table")),
            ("bug", TypeError("oops")),
        ]
    )
    def test_errors_fail_open(self, _, error):
        with (
            patch.object(BlockRule, "blocks_site", side_effect=error),
            self.assertLogs("web.middleware", level="ERROR"),
        ):
            response = self.get("203.0.113.7")
        self.assertEqual(response.status_code, 200)

    def test_participation_check_fails_open(self):
        request = self.factory.get("/", HTTP_X_REAL_IP="203.0.113.7")
        with (
            patch.object(
                BlockRule,
                "participation_block",
                side_effect=ProgrammingError("no table"),
            ),
            self.assertLogs("web.middleware", level="ERROR"),
        ):
            self.assertFalse(participation_blocked(request))


class BlockRuleMiddlewareIntegrationTestCase(TestCase):
    """Through the full middleware stack, as configured in settings."""

    def setUp(self):
        # Rolling back a test's rules doesn't clear the cache.
        BlockRule.clear_cache()
        self.addCleanup(BlockRule.clear_cache)
        BlockRule.objects.create(value="203.0.113.7", block_entire_site=True)

    def test_blocked_ip_cannot_reach_site(self):
        response = self.client.get(reverse("web:home"), HTTP_X_REAL_IP="203.0.113.7")
        self.assertContains(response, "Access blocked", status_code=403)

    def test_blocked_ip_cannot_reach_admin(self):
        response = self.client.get("/__CTRL__/", HTTP_X_REAL_IP="203.0.113.7")
        self.assertContains(response, "Access blocked", status_code=403)

    def test_other_ip_reaches_site(self):
        response = self.client.get(reverse("web:home"), HTTP_X_REAL_IP="198.51.100.1")
        self.assertEqual(response.status_code, 200)

    def test_unblocking_takes_effect(self):
        url = reverse("web:home")
        response = self.client.get(url, HTTP_X_REAL_IP="203.0.113.7")
        self.assertEqual(response.status_code, 403)

        BlockRule.objects.get().delete()
        response = self.client.get(url, HTTP_X_REAL_IP="203.0.113.7")
        self.assertEqual(response.status_code, 200)
