import os

from allauth.socialaccount.models import SocialApp
from django.contrib.sites.models import Site

from accounts.models import Organization
from project import settings


def post_migrate_create_organization(sender, **kwargs):
    created, org = Organization.objects.get_or_create(name='MIT', url='https://lookit.mit.edu')


def post_migrate_create_social_app(sender, **kwargs):
    site = Site.objects.first()

    site.domain = settings.SITE_DOMAIN
    site.name = settings.SITE_NAME

    site.save()

    if not SocialApp.objects.exists():
        app = SocialApp.objects.create(
            key='',
            name='OSF',
            provider='osf',
            # Defaults are valid for staging
            client_id=os.environ.get('OSF_OAUTH_CLIENT_ID', '3518b74e12584abf9e48565ff6aee6f3'),
            secret=os.environ.get('OSF_OAUTH_SECRET', 'vYlku3raTL5DnHZlkqCIaShmPVIl1nifsFJCNLxU'),
        )
        app.sites.clear()
        app.sites.add(site)
