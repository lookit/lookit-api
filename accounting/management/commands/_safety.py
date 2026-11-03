"""Guards shared by the development-only ledger commands (seed_ledger, reset_ledger)."""

from django.conf import settings
from django.core.management.base import CommandError

PRODUCTION_ENVIRONMENTS = {"production", "prod"}


def refuse_in_production(command_name):
    if settings.ENVIRONMENT.strip().lower() in PRODUCTION_ENVIRONMENTS:
        raise CommandError(
            f"{command_name} is for development and staging only; "
            f"ENVIRONMENT is {settings.ENVIRONMENT!r}."
        )
