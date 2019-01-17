from django.apps import AppConfig
from django.db.models.signals import post_migrate

from accounts.signals import (post_migrate_create_flatpages,
                              post_migrate_create_organization,
                              post_migrate_create_social_app)


class AccountsConfig(AppConfig):
    name = "accounts"

    def ready(self):
        post_migrate.connect(post_migrate_create_organization, sender=self)
        post_migrate.connect(post_migrate_create_social_app, sender=self)
        post_migrate.connect(post_migrate_create_flatpages, sender=self)
