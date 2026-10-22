"""Shared fixtures for the accounting tests.

They live here rather than in a helpers module because the name-tests-test pre-commit
hook requires every other module under tests/ to be named test_*.py.
"""

import uuid

from django.db import connection, transaction
from django.utils import timezone
from django_dynamic_fixture import G

from accounting import services
from accounting.models import EntryType, GrantType, Lot
from accounts.models import User
from studies.models import Lab, Study, StudyType


def make_lab(**kwargs):
    return G(Lab, **kwargs)


def make_study(lab, **kwargs):
    creator = G(User, is_active=True, is_researcher=True)
    return G(
        Study,
        lab=lab,
        creator=creator,
        study_type=StudyType.get_ember_frame_player(),
        **kwargs,
    )


def make_deficit(lab, unit, amount, *, study=None):
    """A DEFICIT lot overdrawn by ``amount``

    TO DO: This can be replaced with a real deficit-triggering event when
    that is implemented.
    """
    now = timezone.now()
    with transaction.atomic():
        lot = Lot.objects.create(
            lab=lab,
            unit=unit,
            study=study,
            grant_type=GrantType.DEFICIT,
            amount_granted=0,
            amount_remaining=0,
            granted_at=now,
        )
        services._post(
            lot,
            -amount,
            EntryType.CONSUME,
            group_id=uuid.uuid4(),
            effective_at=now,
            study=study,
        )
    lot.refresh_from_db()
    return lot


def drop_constraint(table, name):
    """Drop a database constraint for the rest of the current test transaction.

    Used to plant rows that the schema would otherwise reject, so that check_ledger can
    be shown to catch them. Only for use inside a TestCase, which rolls the DDL back.
    """
    with connection.cursor() as cursor:
        # Flush deferred FK checks, which otherwise block ALTER TABLE.
        cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")
        cursor.execute(f'ALTER TABLE "{table}" DROP CONSTRAINT "{name}"')
