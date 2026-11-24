import threading
from unittest import mock

from django.db import connection
from django.test import TransactionTestCase

from accounting import services
from accounting.invariants import check_invariants
from accounting.models import GrantType, Lot, Unit
from accounting.tests import make_deficit, make_lab


class ConcurrentDeficitSettlementTestCase(TransactionTestCase):
    """Two grants racing to settle the same deficit must not both settle it.

    Uses real transactions and threads so that select_for_update actually serialises
    them; a TestCase would run everything in one transaction on one connection.
    """

    def test_deficit_settled_once(self):
        lab = make_lab()
        deficit = make_deficit(lab, Unit.STUDY_CREDIT, 10)

        real_post = services._post

        def slow_post(*args, **kwargs):
            # Hold the deficit lock long enough for the other thread to queue behind it.
            result = real_post(*args, **kwargs)
            threading.Event().wait(0.2)
            return result

        barrier = threading.Barrier(2)
        errors = []

        def worker():
            try:
                barrier.wait()
                services.grant(lab, 10, Unit.STUDY_CREDIT, GrantType.COMPLIMENTARY)
            except Exception as e:  # noqa: BLE001 - surfaced by the assertion below
                errors.append(e)
            finally:
                connection.close()

        with mock.patch.object(services, "_post", side_effect=slow_post):
            threads = [threading.Thread(target=worker) for _ in range(2)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

        self.assertEqual(errors, [])
        deficit.refresh_from_db()
        self.assertEqual(deficit.amount_remaining, 0)
        new_lots = Lot.objects.filter(lab=lab, grant_type=GrantType.COMPLIMENTARY)
        self.assertEqual(
            sorted(new_lots.values_list("amount_remaining", flat=True)), [0, 10]
        )
        self.assertEqual(services.lab_balance(lab, Unit.STUDY_CREDIT), 10)
        self.assertEqual(check_invariants(), [])
