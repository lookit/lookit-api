from uuid import UUID

from django.test import TestCase
from django_dynamic_fixture import G

from accounts.models import Child
from accounts.utils import hash_child_id, hash_child_id_from_model, hash_id
from studies.models import Response, Study


class AuthenticationTestCase(TestCase):
    def setUp(self):
        self.id1 = UUID("26edcab0-b578-49e4-9ef3-6f9e5ee32642")
        self.id2 = UUID("c39fc4e9-0084-4efb-9db1-ea596c946108")
        self.salt = UUID("88b9d333-852d-42a2-8352-3027354ee136")
        self.length = 6

    def test_hash_id(self):
        """Confirm that hash id return a consistant hash value."""
        self.assertEqual(hash_id(self.id1, self.id2, self.salt, self.length), "2Y7W5d")

    def test_hash_child_id_from_model(self):
        """Compare hash_child_id to the refactored hash_child_id_from_model."""
        resp_dict = {
            "child__uuid": self.id1,
            "study__uuid": self.id2,
            "study__salt": self.salt,
            "study__hash_digits": self.length,
        }

        child_model = G(Child, uuid=self.id1)
        study_model = G(Study, uuid=self.id2, salt=self.salt, hash_digits=self.length)
        resp_model = G(Response, child=child_model, study=study_model)

        self.assertEqual(hash_child_id(resp_dict), hash_child_id_from_model(resp_model))
