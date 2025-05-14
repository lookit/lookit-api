import random
import string
from http import HTTPStatus

from django.test import TestCase
from django.urls import reverse

from accounts.models import GoogleAuthenticatorTOTP, User
from accounts.tests.test_accounts import Force2FAClient


class SetSpamActionTestCase(TestCase):
    def setUp(self):
        self.client = Force2FAClient()

    def random_str(self):
        return "".join(
            random.SystemRandom().choice(string.ascii_uppercase + string.digits)
            for _ in range(10)
        )

    def create_admin_user(self):
        user = User.objects.create_superuser(self.random_str(), self.random_str())
        GoogleAuthenticatorTOTP.objects.create(user=user, activated=True)
        return user

    def create_user(self):
        return User.objects.create_user(username=self.random_str())

    def url(self):
        return reverse("admin:accounts_user_changelist")

    def test_set_as_spam_only_spammer_changed(self):
        admin = self.create_admin_user()
        spammer = self.create_user()
        user = self.create_user()
        admin_comments = self.random_str()

        self.client.force_login(admin)

        data = {
            "action": "set_selected_as_spam",
            "_selected_action": [spammer.id],
            "post": "yes",
            "admin_comments": admin_comments,
        }
        response = self.client.post(self.url(), data=data, follow=True)

        user = User.objects.get(pk=user.id)

        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertFalse(user.is_spam)
        self.assertTrue(
            all(
                getattr(user, x) for x in user.__dict__.keys() if x.startswith("email_")
            )
        )
        self.assertTrue(user.is_active)
        self.assertEqual(user.admin_comments, "")

    def test_set_as_spam_one_user(self):
        user = self.create_admin_user()
        spammer = self.create_user()
        admin_comments = self.random_str()

        self.client.force_login(user)

        data = {
            "action": "set_selected_as_spam",
            "_selected_action": [spammer.id],
            "post": "yes",
            "admin_comments": admin_comments,
        }
        response = self.client.post(self.url(), data=data, follow=True)

        spammer = User.objects.get(pk=spammer.id)

        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTrue(spammer.is_spam)
        self.assertFalse(
            all(
                getattr(spammer, x)
                for x in spammer.__dict__.keys()
                if x.startswith("email_")
            )
        )
        self.assertFalse(spammer.is_active)
        self.assertEqual(spammer.admin_comments, admin_comments)

    def test_set_as_spam_many_users(self):
        user = self.create_admin_user()
        spammers = [self.create_user() for _ in range(10)]

        self.client.force_login(user)

        for idx in range(10):
            admin_comments = self.random_str()
            data = {
                "action": "set_selected_as_spam",
                "_selected_action": [s.id for s in spammers],
                "user_idx": idx,
                "post": "yes",
                "admin_comments": admin_comments,
            }
            response = self.client.post(self.url(), data=data, follow=True)

            spammer = User.objects.get(pk=spammers[idx].id)

            self.assertEqual(response.status_code, HTTPStatus.OK)
            self.assertTrue(spammer.is_spam, idx)
            self.assertFalse(
                all(
                    getattr(spammer, x)
                    for x in spammer.__dict__.keys()
                    if x.startswith("email_")
                )
            )
            self.assertFalse(spammer.is_active)
            self.assertEqual(spammer.admin_comments, admin_comments)
