import csv
import datetime
import io
import json
import string

from django.db.models import Prefetch, QuerySet
from django.http import HttpResponseRedirect
from django.shortcuts import redirect, reverse
from django.views.generic.detail import SingleObjectMixin
from guardian.mixins import PermissionRequiredMixin
from guardian.shortcuts import get_objects_for_user

import attachment_helpers
from accounts.models import Child, User
from accounts.utils import hash_id
from exp.utils import csv_dict_output_and_writer, flatten_dict, round_age
from exp.views.mixins import ExperimenterLoginRequiredMixin
from studies.models import Response, Study


class StudyResponsesMixin(
	SingleObjectMixin, ExperimenterLoginRequiredMixin, PermissionRequiredMixin
):
	"""
	Mixin with shared items for StudyResponsesList and StudyResponsesAll views
	"""

	permission_required = "studies.can_view_study_responses"
	raise_exception = True

	age_data_options = [
		{
			"id": "rounded",
			"name": "Rounded age",
			"column": "child_age_rounded",
			"default": True,
		},
		{"id": "exact", "name": "Age in days", "column": "child_age_in_days"},
		{"id": "birthday", "name": "Birthdate", "column": "child_birthday"},
	]
	child_data_options = [
		{"id": "name", "name": "Child name", "column": "child_name"},
		{
			"id": "globalchild",
			"name": "Child global ID",
			"column": "child_global_id",
			"default": False,
		},
		{
			"id": "gender",
			"name": "Child gender",
			"column": "child_gender",
			"default": True,
		},
		{
			"id": "gestage",
			"name": "Child gestational age",
			"column": "child_age_at_birth",
		},
		{
			"id": "conditions",
			"name": "Child conditions",
			"column": "child_characteristics",
			"default": True,
		},
		{
			"id": "languages",
			"name": "Child languages",
			"column": "child_languages",
			"default": True,
		},
		{
			"id": "addl",
			"name": "Child additional info",
			"column": "child_additional_information",
		},
		{"id": "parent", "name": "Parent name", "column": "participant_nickname"},
		{
			"id": "globalparent",
			"name": "Parent global ID",
			"column": "participant_global_id",
			"default": False,
		},
	]
	identifiable_data_options = [
		"exact",
		"birthday",
		"name",
		"addl",
		"parent",
		"globalchild",
		"globalparent",
	]
	all_optional_header_keys = [
		option["id"] for option in age_data_options + child_data_options
	]

	def get_response_headers(
		self, optional_headers_selected_ids, all_headers_available
	):
		standard_headers = self.get_response_headers_and_row_data()["headers"]
		optional_headers = [
			option["column"]
			for option in self.age_data_options + self.child_data_options
		]
		selected_headers = [
			option["column"]
			for option in self.age_data_options + self.child_data_options
			if option["id"] in optional_headers_selected_ids
		]
		standard_headers_selected_only = [
			header
			for header in standard_headers
			if header not in optional_headers or header in selected_headers
		]
		ordered_headers = standard_headers_selected_only + sorted(
			list(all_headers_available - set(standard_headers))
		)
		return ordered_headers

	def build_responses_json(self, responses, optional_headers=None):
		"""
		Builds the JSON response data for the researcher to download
		"""
		json_responses = []
		if optional_headers == None:
			optional_headers = []
		for resp in responses:
			age_in_days = (resp.date_created.date() - resp.child.birthday).days
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
						"date_created": resp.date_created,
						"withdrawn": resp.withdrawn,
					},
					"study": {"uuid": str(resp.study.uuid)},
					"participant": {
						"global_id": str(resp.child.user.uuid)
						if "globalparent" in optional_headers
						else "",
						"hashed_id": hash_id(
							resp.child.user.uuid,
							resp.study.uuid,
							resp.study.salt,
							resp.study.hash_digits,
						),
						"nickname": resp.child.user.nickname
						if "parent" in optional_headers
						else "",
					},
					"child": {
						"global_id": str(resp.child.uuid)
						if "globalchild" in optional_headers
						else "",
						"hashed_id": hash_id(
							resp.child.uuid,
							resp.study.uuid,
							resp.study.salt,
							resp.study.hash_digits,
						),
						"name": resp.child.given_name
						if "name" in optional_headers
						else "",
						"birthday": resp.child.birthday
						if "birthday" in optional_headers
						else "",
						"age_in_days": age_in_days
						if "exact" in optional_headers
						else "",
						"age_rounded": str(round_age(int(age_in_days)))
						if "rounded" in optional_headers
						else "",
						"gender": resp.child.gender
						if "gender" in optional_headers
						else "",
						"language_list": resp.child.language_list
						if "languages" in optional_headers
						else "",
						"condition_list": resp.child.condition_list
						if "conditions" in optional_headers
						else "",
						"age_at_birth": resp.child.age_at_birth
						if "gestage" in optional_headers
						else "",
						"additional_information": resp.child.additional_information
						if "addl" in optional_headers
						else "",
					},
					"consent": resp.current_consent_details,
				}
			)
		return json_responses

	def get_response_headers_and_row_data(self, resp=None):

		age_in_days = (
			(resp.date_created.date() - resp.child.birthday).days if resp else ""
		)

		all_row_data = [
			("response_id", resp.id if resp else "", "Short ID for this response"),
			(
				"response_uuid",
				str(resp.uuid) if resp else "",
				"Unique identifier for response. Can be used to match data to video filenames.",
			),
			(
				"response_date_created",
				str(resp.date_created) if resp else "",
				"Timestamp for when participant began session, in format e.g. 2019-11-07 17:13:38.702958+00:00",
			),
			(
				"response_completed",
				resp.completed if resp else "",
				"Whether the participant submitted the exit survey; depending on study criteria, this may not align with whether the session is considered complete. E.g., participant may have left early but submitted exit survey, or may have completed all test trials but not exit survey.",
			),
			(
				"response_withdrawn",
				resp.withdrawn if resp else "",
				"Whether the participant withdrew permission for viewing/use of study video beyond consent video. If true, video will not be available and must not be used.",
			),
			(
				"response_consent_ruling",
				resp.most_recent_ruling if resp else "",
				"Most recent consent video ruling: one of 'accepted' (consent has been reviewed and judged to indidate informed consent), 'rejected' (consent has been reviewed and judged not to indicate informed consent -- e.g., video missing or parent did not read statement), or 'pending' (no current judgement, e.g. has not been reviewed yet or waiting on parent email response')",
			),
			(
				"response_consent_arbiter",
				resp.most_recent_ruling_arbiter if resp else "",
				"Name associated with researcher account that made the most recent consent ruling",
			),
			(
				"response_consent_time",
				resp.most_recent_ruling_date if resp else "",
				"Timestamp of most recent consent ruling, format e.g. 2019-12-09 20:40",
			),
			(
				"response_consent_comment",
				resp.most_recent_ruling_comment if resp else "",
				"Comment associated with most recent consent ruling (may be used to track e.g. any cases where consent was confirmed by email)",
			),
			(
				"study_uuid",
				str(resp.study.uuid) if resp else "",
				"Unique identifier of study associated with this response. Same for all responses to a given Lookit study.",
			),
			(
				"participant_global_id",
				str(resp.child.user.uuid) if resp else "",
				"Unique identifier for family account associated with this response. Will be the same for multiple responses from a child and for siblings, and across different studies. MUST BE REDACTED FOR PUBLICATION because this allows identification of families across different published studies, which may have unintended privacy consequences. Researchers can use this ID to match participants across studies (subject to their own IRB review), but would need to generate their own random participant IDs for publication in that case. Use participant_hashed_id as a publication-safe alternative if only analyzing data from one Lookit study.",
			),
			(
				"participant_hashed_id",
				hash_id(
					resp.child.user.uuid,
					resp.study.uuid,
					resp.study.salt,
					resp.study.hash_digits,
				)
				if resp
				else "",
				"Identifier for family account associated with this response. Will be the same for multiple responses from a child and for siblings, but is unique to this study. This may be published directly.",
			),
			(
				"participant_nickname",
				resp.child.user.nickname if resp else "",
				"Nickname associated with the family account for this response - generally the mom or dad's name. Must be redacted for publication.",
			),
			(
				"child_global_id",
				str(resp.child.uuid) if resp else "",
				"Primary unique identifier for the child associated with this response. Will be the same for multiple responses from one child, even across different Lookit studies. MUST BE REDACTED FOR PUBLICATION because this allows identification of children across different published studies, which may have unintended privacy consequences. Researchers can use this ID to match participants across studies (subject to their own IRB review), but would need to generate their own random participant IDs for publication in that case. Use child_hashed_id as a publication-safe alternative if only analyzing data from one Lookit study.",
			),
			(
				"child_hashed_id",
				hash_id(
					resp.child.uuid,
					resp.study.uuid,
					resp.study.salt,
					resp.study.hash_digits,
				)
				if resp
				else "",
				"Identifier for child associated with this response. Will be the same for multiple responses from a child, but is unique to this study. This may be published directly.",
			),
			(
				"child_name",
				resp.child.given_name if resp else "",
				"Nickname for the child associated with this response. Not necessarily a real name (we encourage initials, nicknames, etc. if parents aren't comfortable providing a name) but must be redacted for publication of data.",
			),
			(
				"child_birthday",
				resp.child.birthday if resp else "",
				"Birthdate of child associated with this response. Must be redacted for publication of data (switch to age at time of participation; either use rounded age, jitter the age, or redact timestamps of participation).",
			),
			(
				"child_age_in_days",
				age_in_days,
				"Age in days at time of response of child associated with this response, exact. This can be used in conjunction with timestamps to calculate the child's birthdate, so must be jittered or redacted prior to publication unless no timestamp information is shared.",
			),
			(
				"child_age_rounded",
				str(round_age(int(age_in_days))) if age_in_days else "",
				"Age in days at time of response of child associated with this response, rounded to the nearest 10 days if under 1 year old and to the nearest 30 days if over 1 year old. May be published; however, if you have more than a few sessions per participant it would be possible to infer the exact age in days (and therefore birthdate) with some effort. In this case you might consider directly jittering birthdates.",
			),
			(
				"child_gender",
				resp.child.gender if resp else "",
				"Parent-identified gender of child, one of 'm' (male), 'f' (female), 'o' (other), or 'na' (prefer not to answer)",
			),
			(
				"child_age_at_birth",
				resp.child.age_at_birth if resp else "",
				"Gestational age at birth in weeks. One of '40 or more weeks', '39 weeks' through '24 weeks', 'Under 24 weeks', or 'Not sure or prefer not to answer'",
			),
			(
				"child_language_list",
				resp.child.language_list if resp else "",
				"List of languages spoken (using language codes in Lookit docs), separated by spaces",
			),
			(
				"child_condition_list",
				resp.child.condition_list if resp else "",
				"List of child characteristics (using condition/characteristic codes in Lookit docs), separated by spaces",
			),
			(
				"child_additional_information",
				resp.child.additional_information if resp else "",
				"Free response 'anything else you'd like us to know' field on child registration form for child associated with this response. Should be redacted or reviewed prior to publication as it may include names or other identifying information.",
			),
			(
				"response_sequence",
				resp.sequence if resp else [],
				"Each response_sequence.N field (response_sequence.0, response_sequence.1, etc.) gives the ID of the Nth frame displayed during the session associated with this response. Responses may have different sequences due to randomization or if a participant leaves early.",
			),
			(
				"response_conditions",
				[
					{**{"frameName": condFrame}, **conds}
					for (condFrame, conds) in resp.conditions.items()
				]
				if resp
				else [],
				"RESEARCHERS: EXPAND THIS SECTION BASED ON YOUR INDIVIDUAL STUDY. Each set of response_conditions.N.(...) fields give information about condition assignment during a particular frame of this study. response_conditions.0.frameName is the frame ID (corresponding to a value in response_sequence) where the randomization occured. Additional fields such as response_conditions.0.conditionNum depend on the specific randomizer frames used in this study.",
			),
		]

		headers_ordered = [name for (name, val, desc) in all_row_data][0:-2]

		field_descriptions = {name: desc for (name, val, desc) in all_row_data}

		row_data_with_headers = flatten_dict(
			{name: val for (name, val, desc) in all_row_data}
		)

		return {
			"headers": headers_ordered,
			"descriptions": field_descriptions,
			"dict": row_data_with_headers,
		}

	def get_frame_data(self, resp):
	
		if type(resp) is not dict:
			resp = {
				"child__uuid": resp.child.uuid,
				"study__uuid": resp.study.uuid,
				"study__salt": resp.study.salt,
				"study__hash_digits": resp.study.hash_digits,
				"uuid": resp.uuid,
				"exp_data": resp.exp_data,
				"global_event_timings": resp.global_event_timings
			}

		frame_data_dicts = []
		child_hashed_id = hash_id(
			resp["child__uuid"], resp["study__uuid"], resp["study__salt"], resp["study__hash_digits"]
		)

		# First add all of the global event timings as events with frame_id "global"
		for (iEvent, event) in enumerate(resp["global_event_timings"]):
			for (key, value) in event.items():
				frame_data_dicts.append(
					{
						"child_hashed_id": child_hashed_id,
						"response_uuid": str(resp["uuid"]),
						"frame_id": "global",
						"key": key,
						"event_number": str(iEvent),
						"value": value,
					}
				)

		# Next add all data in exp_data
		event_prefix = "eventTimings."
		for (frame_id, frame_data) in resp["exp_data"].items():
			for (key, value) in flatten_dict(frame_data).items():
				# Process event data separately and include event_number within frame
				if key.startswith(event_prefix):
					key_pieces = key.split(".")
					frame_data_dicts.append(
						{
							"child_hashed_id": child_hashed_id,
							"response_uuid": str(resp["uuid"]),
							"frame_id": frame_id,
							"key": ".".join(key_pieces[2:]),
							"event_number": str(key_pieces[1]),
							"value": value,
						}
					)
					# omit frameType values from CSV
				elif key == "frameType":
					continue
					# Omit empty generatedProperties values from CSV
				elif key == "generatedProperties" and not (value):
					continue
					# For all other data, create a regular entry with frame_id and no event #
				else:
					frame_data_dicts.append(
						{
							"child_hashed_id": child_hashed_id,
							"response_uuid": str(resp["uuid"]),
							"frame_id": frame_id,
							"key": key,
							"event_number": "",
							"value": value,
						}
					)

		headers = [
			(
				"response_uuid",
				"Unique identifier for this response; can be matched to summary data and video filenames",
			),
			(
				"child_hashed_id",
				"Hashed identifier for the child associated with this response; can be matched to summary data child_hashed_id. This random ID may be published directly; it is specific to this study. If you need to match children across multiple studies, use the child_global_id.",
			),
			(
				"frame_id",
				"Identifier for the particular frame responsible for this data; matches up to an element in the response_sequence in the summary data file",
			),
			(
				"event_number",
				"Index of the event responsible for this data, if this is an event. Indexes start from 0 within each frame (and within global data) within each response.",
			),
			(
				"key",
				"Label for a piece of data collected during this frame - for example, 'formData.child_favorite_animal'",
			),
			(
				"value",
				"Value of the data associated with this key (of the indexed event if applicable) - for example, 'giraffe'",
			),
		]

		return {
			"data": frame_data_dicts,
			"data_headers": [header for (header, description) in headers],
			"header_descriptions": headers,
		}

	def build_summary_csv(self, responses, optional_headers_selected_ids):
		"""
		Builds CSV file contents for overview of all responses
		"""

		headers = set()
		session_list = []

		for resp in responses:
			row_data = self.get_response_headers_and_row_data(resp)["dict"]
			# Add any new headers from this session
			headers = headers | set(row_data.keys())
			session_list.append(row_data)

		headerList = self.get_response_headers(optional_headers_selected_ids, headers)
		output, writer = csv_dict_output_and_writer(headerList)
		writer.writerows(session_list)
		return output.getvalue()

	def build_framedata_csv(self, responses):
		"""
		Builds CSV file contents for frame-level data from all responses
		"""

		headers = self.get_frame_data(responses[0])["data_headers"]
		output, writer = csv_dict_output_and_writer(headers)

		for resp in responses:
			this_resp_data = self.get_frame_data(resp)
			writer.writerows(this_resp_data["data"])

		return output.getvalue()
