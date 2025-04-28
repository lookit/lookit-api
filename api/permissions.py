import hashlib
import hmac
import json

from django.conf import settings
from django.shortcuts import get_object_or_404
from rest_framework import exceptions, permissions

from accounts.models import Child
from studies.models import Response
from studies.permissions import StudyPermission


class FeedbackPermissions(permissions.BasePermission):
    def has_permission(self, request, view):
        """
        Only have permission to create the feedback if the user has permission to
        edit the associated study.
        """
        if request.method not in permissions.SAFE_METHODS:
            response = request.data.get("response")
            if response and response.get("id"):
                related_study = get_object_or_404(Response, id=response.get("id")).study
                user = request.user
                if not user.has_study_perms(
                    StudyPermission.EDIT_STUDY_FEEDBACK, related_study
                ):
                    return False
        return True


class ResponsePermissions(permissions.BasePermission):
    def has_permission(self, request, view):
        """
        Only have permission to create a response if the user is the parent of the
        associated child
        """
        if request.method not in permissions.SAFE_METHODS:
            child_id = request.data.get("child")
            if child_id and child_id.get("id"):
                child = get_object_or_404(Child, id=child_id.get("id"))
                if child.user != request.user:
                    return False
        return True


class VideoFromS3Permissions:
    def has_permission(self, request, view):
        """
        Only allow the creation of a new video via the API if request is signed and signature is verified.
        Only check the signature on POST requests (other methods will be rejected via the view).
        """
        if request.method == "POST":
            try:
                signature_received = request.META["HTTP_X_AWS_LAMBDA_HMAC_SIG"]
            except KeyError:
                try:
                    signature_received = request.META["headers"][
                        "X_AWS_LAMBDA_HMAC_SIG"
                    ]
                except KeyError:
                    # results in 401 unauthorized response
                    raise exceptions.AuthenticationFailed(
                        "No HMAC signature found in request header."
                    )

            # calculate signature to compare with the one sent
            key = bytes(settings.AWS_LAMBDA_SECRET_ACCESS_KEY, "UTF-8")
            # remove study/response relationships from request data dict to match the content/format sent by client
            request_data = request.data.copy()
            try:
                request_data.pop("study")
            except KeyError:
                raise exceptions.ParseError("Missing required relationship: study")

            try:
                request_data.pop("response")
            except KeyError:
                raise exceptions.ParseError("Missing required relationship: response")

            message = bytes(json.dumps(request_data, separators=(",", ":")), "UTF-8")
            signature_calculated = hmac.new(key, message, hashlib.sha256).hexdigest()

            # false results in 401 unauthorized response
            if not signature_received == signature_calculated:
                raise exceptions.AuthenticationFailed("HMAC signatures do not match.")
            else:
                return True
        else:
            return True
