import json
from django.test import TestCase
from rest_framework.test import APITestCase
from rest_framework.test import APIClient
from rest_framework import status
from django.urls import reverse

from guardian.shortcuts import assign_perm
from studies.models import Response, Study, Feedback
from accounts.models import Child, User
from django_dynamic_fixture import G

# class FilterByUrlKwargsMixinTestCase(TestCase):
#     def test_child_user(self):
#         user = G(User)
#         barren_user = G(User)
#         child = G(Child, user=user)
#
#         client = APIClient()
#
#         response = client.get(f'/api/v1/children/{child.uuid}/users/', format='json')
#         import ipdb; ipdb.set_trace()
