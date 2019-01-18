import json

from django.test import TestCase
from django.urls import reverse
from django_dynamic_fixture import G
from guardian.shortcuts import assign_perm
from rest_framework import status
from rest_framework.test import APIClient, APITestCase

from accounts.models import Child, User
from studies.models import Feedback, Response, Study

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
