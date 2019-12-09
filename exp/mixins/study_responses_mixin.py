import csv
import datetime
import io
import json

from django.db.models import Prefetch, QuerySet
from django.http import HttpResponseRedirect
from django.shortcuts import redirect, reverse
from django.views.generic.detail import SingleObjectMixin
from guardian.mixins import PermissionRequiredMixin
from guardian.shortcuts import get_objects_for_user

import attachment_helpers
from accounts.models import Child, User
from exp.views.mixins import ExperimenterLoginRequiredMixin
from studies.models import Response, Study


# PREFETCH = Response.objects.filter(completed_consent_frame=True)
# CHILDREN_WITH_USERS = Child.objects.select_related("user")
WITH_PREFETCHED_RESPONSES = Study.objects.prefetch_related("responses", "videos")


def flatten_dict(d):
	'''Flatten a dictionary where values may be other dictionaries

	The dictionary returned will have keys created by joining higher- to lower-level keys with dots. e.g. if the original dict d is
	{'a': {'x':3, 'y':4}, 'b':{'z':5}, 'c':{} }
	then the dict returned will be
	{'a.x':3, 'a.y': 4, 'b.z':5}

	Note that if a key is mapped to an empty dict or list, NO key in the returned dict is created for this key.

	Also note that values may be overwritten if there is conflicting dot notation in the input dictionary, e.g. {'a': {'x': 3}, 'a.x': 4}.
	'''
	# http://codereview.stackexchange.com/a/21035

	def expand(key, value):
		if isinstance(value, list):
			value = {i: v for (i, v) in enumerate(value)}
		if isinstance(value, dict):
			return [ (str(key) + '.' + str(k), v) for k, v in flatten_dict(value).items() ]
		else:
			return [ (key, value) ]

	items = [ item for k, v in d.items() for item in expand(k, v) ]

	return dict(items)
	
def merge_dicts(d1, d2):
	d1_copy = d1.copy()
	d1_copy.update(d2)
	return d1_copy

class StudyResponsesMixin(
	SingleObjectMixin, ExperimenterLoginRequiredMixin, PermissionRequiredMixin
):
	"""
	Mixin with shared items for StudyResponsesList, StudyResponsesAll, and StudyAttachments Views.

	TODO: deprecate this beast
	"""

	queryset = WITH_PREFETCHED_RESPONSES
	permission_required = "studies.can_view_study_responses"
	raise_exception = True

	def convert_to_string(self, object):
		if isinstance(object, datetime.date):
			return object.__str__()
		return object

	def build_participant_data(self, responses):
		json_responses = []
		for resp in responses:
			latest_dem = resp.demographic_snapshot
			json_responses.append(
				json.dumps(
					{
						"response": {"id": resp.id, "uuid": str(resp.uuid)},
						"participant": {
							"id": resp.child.user_id,
							"uuid": str(resp.child.user.uuid),
							"nickname": resp.child.user.nickname,
						},
						"demographic_snapshot": {
							"demographic_id": latest_dem.id,
							"uuid": str(latest_dem.uuid),
							"number_of_children": latest_dem.number_of_children,
							"child_birthdays": latest_dem.child_birthdays,
							"languages_spoken_at_home": latest_dem.languages_spoken_at_home,
							"number_of_guardians": latest_dem.number_of_guardians,
							"number_of_guardians_explanation": latest_dem.number_of_guardians_explanation,
							"race_identification": latest_dem.race_identification,
							"age": latest_dem.age,
							"gender": latest_dem.gender,
							"education_level": latest_dem.gender,
							"spouse_education_level": latest_dem.spouse_education_level,
							"annual_income": latest_dem.annual_income,
							"number_of_books": latest_dem.number_of_books,
							"additional_comments": latest_dem.additional_comments,
							"country": latest_dem.country.name,
							"state": latest_dem.state,
							"density": latest_dem.density,
							"lookit_referrer": latest_dem.lookit_referrer,
							"extra": latest_dem.extra,
						},
					},
					indent=4,
					default=self.convert_to_string,
				)
			)
		return json_responses

	def build_csv_participant_row_data(self, resp):
		"""
		Returns row of csv participant data
		"""
		latest_dem = resp.demographic_snapshot

		return [
			resp.id,
			str(resp.uuid),
			resp.child.user_id,
			str(resp.child.user.uuid),
			resp.child.user.nickname,
			latest_dem.id,
			str(latest_dem.uuid),
			latest_dem.number_of_children,
			[
				self.convert_to_string(birthday)
				for birthday in latest_dem.child_birthdays
			],
			latest_dem.languages_spoken_at_home,
			latest_dem.number_of_guardians,
			latest_dem.number_of_guardians_explanation,
			latest_dem.race_identification,
			latest_dem.age,
			latest_dem.gender,
			latest_dem.education_level,
			latest_dem.spouse_education_level,
			latest_dem.annual_income,
			latest_dem.number_of_books,
			latest_dem.additional_comments,
			latest_dem.country.name,
			latest_dem.state,
			latest_dem.density,
			latest_dem.lookit_referrer,
			latest_dem.extra,
		]

	def get_csv_participant_headers(self):
		"""
		Returns header row for csv participant data
		"""
		return [
			"response_id",
			"response_uuid",
			"participant_id",
			"participant_uuid",
			"participant_nickname",
			"demographic_id",
			"latest_dem_uuid",
			"demographic_number_of_children",
			"demographic_child_birthdays",
			"demographic_languages_spoken_at_home",
			"demographic_number_of_guardians",
			"demographic_number_of_guardians_explanation",
			"demographic_race_identification",
			"demographic_age",
			"demographic_gender",
			"demographic_education_level",
			"demographic_spouse_education_level",
			"demographic_annual_income",
			"demographic_number_of_books",
			"demographic_additional_comments",
			"demographic_country",
			"demographic_state",
			"demographic_density",
			"demographic_lookit_referrer",
			"demographic_extra",
		]

	def build_responses(self, responses):
		"""
		Builds the JSON response data for the researcher to download
		"""
		json_responses = []
		for resp in responses:
			json_responses.append(
				{
					"response": {
						"id": resp.id,
						"uuid": str(resp.uuid),
						"sequence": resp.sequence,
						"conditions": resp.conditions,
						"exp_data": resp.exp_data,
						"global_event_timings": resp.global_event_timings,
						"completed": resp.completed,
						"withdrawn": resp.withdrawn,
					},
					"study": {"id": resp.study.id, "uuid": str(resp.study.uuid)},
					"participant": {
						"id": resp.child.user_id,
						"uuid": str(resp.child.user.uuid),
						"nickname": resp.child.user.nickname,
					},
					"child": {
						"id": resp.child.id,
						"uuid": str(resp.child.uuid),
						"name": resp.child.given_name,
						"birthday": resp.child.birthday,
						"gender": resp.child.gender,
						"age_at_birth": resp.child.age_at_birth,
						"additional_information": resp.child.additional_information,
					},
					"consent_information": resp.current_consent_details,
				}
			)
		return json_responses

	def csv_output_and_writer(self):
		output = io.StringIO()
		return output, csv.writer(output, quoting=csv.QUOTE_NONNUMERIC)
		
	def csv_dict_output_and_writer(self, headerList):
		output = io.StringIO()
		writer = csv.DictWriter(output, quoting=csv.QUOTE_NONNUMERIC, fieldnames=headerList, restval='', extrasaction='ignore')
		writer.writeheader()
		return output, writer
		
	def get_ordered_csv_headers_for_row_data(self):
		''' Returns the CSV headers to display first in the individual/all responses CSVs.
		These can be freely rearranged per preference, but should be a subset of the keys 
		returned by get_csv_headers_and_row_data.'''
		
		return [
			"response_id",
			"response_uuid",
			"response_completed", 
			"response_withdrawn",
			"response_consent_ruling", 
			"response_consent_arbiter", 
			"response_consent_time", 
			"response_consent_comment", 
			"study_id", 
			"study_uuid", 
			"participant_id", 
			"participant_uuid", 
			"participant_nickname", 
			"child_id", 
			"child_uuid", 
			"child_name", 
			"child_birthday", 
			"child_gender", 
			"child_age_at_birth", 
			"child_additional_information", 
		]

	def get_csv_headers_and_row_data(self, resp={}):

		row_data_with_headers = {
			"response_id": resp.id if resp else '',
			"response_uuid": str(resp.uuid) if resp else '',
			"response_completed": resp.completed if resp else '', 
			"response_withdrawn": resp.withdrawn if resp else '',
			"response_sequence": resp.sequence if resp else [],
			"response_conditions": [merge_dicts({'frameName': condFrame}, conds) for (condFrame, conds) in resp.conditions.items()] if resp else [],
			"response_consent_ruling": resp.most_recent_ruling if resp else '', 
			"response_consent_arbiter": resp.most_recent_ruling_arbiter if resp else '', 
			"response_consent_time": resp.most_recent_ruling_date if resp else '', 
			"response_consent_comment": resp.most_recent_ruling_comment if resp else '', 
			"study_id": resp.study.id if resp else '', 
			"study_uuid": str(resp.study.uuid) if resp else '', 
			"participant_id": resp.child.user_id if resp else '', 
			"participant_uuid": str(resp.child.user.uuid) if resp else '', 
			"participant_nickname": resp.child.user.nickname if resp else '', 
			"child_id": resp.child.id if resp else '', 
			"child_uuid": str(resp.child.uuid) if resp else '', 
			"child_name": resp.child.given_name if resp else '', 
			"child_birthday": resp.child.birthday if resp else '', 
			"child_gender": resp.child.gender if resp else '', 
			"child_age_at_birth": resp.child.age_at_birth if resp else '', 
			"child_additional_information": resp.child.additional_information if resp else '', 
		}
		
		return flatten_dict(row_data_with_headers)
		
		   #(resp.exp_data, ## remove
			#(resp.global_event_timings

	def post(self, request, *args, **kwargs):
		"""
		Downloads a single study video.
		"""
		attachment_id = self.request.POST.get("attachment")
		if attachment_id:
			download_url = self.get_object().videos.get(pk=attachment_id).download_url
			return redirect(download_url)

		return HttpResponseRedirect(
			reverse("exp:study-responses-list", kwargs=dict(pk=self.get_object().pk))
		)
