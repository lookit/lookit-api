import uuid
from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import F, Q
from django.utils import timezone

from accounting import services
from accounting.management.commands._safety import refuse_in_production
from accounting.models import EntryType, GrantType, Lot, Unit
from studies.models import Lab

SEED_NOTE = "Fake data from seed_ledger"
# These are shared labs created by studies migration 0066, and excluded from lab selection by default.
EXCLUDED_LAB_NAMES = ("Sandbox lab", "Demo lab")


class Command(BaseCommand):
    help = (
        "Add a small set of fake lots to one lab for testing the lots and ledger."
        "This produces unassigned points, a study allowance, a future-dated grant, "
        "study credits, and a credit deficit that a later grant settles. Adds to "
        "whatever is already there, so run reset_ledger first for a clean slate. "
        "Refuses to run when ENVIRONMENT is production."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--lab",
            type=int,
            help="Primary key of the lab to seed. Defaults to the first lab that has "
            "at least one study (other than the Sandbox lab and Demo lab).",
        )

    def handle(self, *args, lab=None, **options):
        refuse_in_production("seed_ledger")
        lab = self._get_lab(lab)
        study = lab.studies.order_by("pk").first()
        now = timezone.now()
        seed = {"notes": SEED_NOTE, "memo": SEED_NOTE}

        with transaction.atomic():
            services.grant(
                lab,
                1000,
                Unit.POINT,
                GrantType.TOP_UP,
                expires_at=now + timedelta(days=365),
                **seed,
            )
            services.grant(
                lab,
                200,
                Unit.POINT,
                GrantType.STUDY_ALLOWANCE,
                study=study,
                **seed,
            )
            services.grant(
                lab,
                500,
                Unit.POINT,
                GrantType.MEMBERSHIP,
                granted_at=now + timedelta(days=30),
                expires_at=now + timedelta(days=395),
                **seed,
            )
            services.grant(lab, 2, Unit.STUDY_CREDIT, GrantType.COMPLIMENTARY, **seed)
            # Spend 3 credits with only 2 on hand, leaving a deficit of 1. Then grant 5.
            # The grant automatically settles the deficit of 1 from the new lot.
            self._spend(lab, Unit.STUDY_CREDIT, 3)
            services.grant(lab, 5, Unit.STUDY_CREDIT, GrantType.COMPLIMENTARY, **seed)

        self.stdout.write(
            self.style.SUCCESS(
                f"Seeded lab {lab.pk} ({lab.name}); study allowance on study "
                f"{study.pk} ({study.name})."
            )
        )
        for unit in Unit:
            self.stdout.write(
                f"\n{unit.label} balance: {services.lab_balance(lab, unit)}"
            )
            for lot in services.lot_balances(lab, unit):
                scope = f"study {lot.study_id}" if lot.study_id else "lab"
                self.stdout.write(
                    f"  {lot.get_grant_type_display():<20} {scope:<12} "
                    f"granted {lot.granted_at:%Y-%m-%d}  balance {lot.balance}"
                )

    def _get_lab(self, pk):
        if pk is not None:
            try:
                lab = Lab.objects.get(pk=pk)
            except Lab.DoesNotExist:
                raise CommandError(f"No lab with primary key {pk}.")
            if not lab.studies.exists():
                raise CommandError(f"Lab {pk} has no studies to give an allowance to.")
            return lab
        lab = (
            Lab.objects.filter(study__isnull=False)
            .exclude(name__in=EXCLUDED_LAB_NAMES)
            .distinct()
            .order_by("pk")
            .first()
        )
        if lab is None:
            raise CommandError(
                "No lab (other than the Sandbox lab and Demo lab) has a study. "
                "Create a study (and a new lab, if necessary) or pass --lab "
                "to seed either the Sandbox or Demo lab."
            )
        return lab

    def _spend(self, lab, unit, amount):
        """Spend ``amount`` from the lab's lab-level lots.

        Draws from the active lots in spend order, and puts whatever they cannot
        cover on the deficit lot. This writes the CONSUME rows through the same
        ledger primitive the services use. Reuses the lab's deficit lot if one exists,
        since there can be only one per lab and unit.
        """
        now = timezone.now()
        group_id = uuid.uuid4()
        active_lots = (
            Lot.objects.select_for_update()
            .filter(
                lab=lab,
                unit=unit,
                study__isnull=True,
                granted_at__lte=now,
                expired_at__isnull=True,
                amount_remaining__gt=0,
            )
            .filter(Q(expires_at__isnull=True) | Q(expires_at__gt=now))
            .exclude(grant_type=GrantType.DEFICIT)
            .order_by(
                "consumption_priority",
                F("expires_at").asc(nulls_last=True),
                "granted_at",
                "id",
            )
        )
        for lot in active_lots:
            if amount == 0:
                return
            take = min(amount, lot.amount_remaining)
            services._post(
                lot,
                -take,
                EntryType.CONSUME,
                group_id=group_id,
                effective_at=now,
                memo=SEED_NOTE,
            )
            amount -= take
        if amount == 0:
            return

        deficit = (
            Lot.objects.select_for_update()
            .filter(
                lab=lab, unit=unit, grant_type=GrantType.DEFICIT, study__isnull=True
            )
            .first()
        )
        if deficit is None:
            deficit = Lot.objects.create(
                lab=lab,
                unit=unit,
                grant_type=GrantType.DEFICIT,
                amount_granted=0,
                amount_remaining=0,
                granted_at=now,
                notes=SEED_NOTE,
            )
        services._post(
            deficit,
            -amount,
            EntryType.CONSUME,
            group_id=group_id,
            effective_at=now,
            memo=SEED_NOTE,
        )
