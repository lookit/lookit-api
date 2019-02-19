from django.shortcuts import get_object_or_404
from rest_framework import permissions

from accounts.models import Child
from studies.models import Response


class FeedbackPermissions(permissions.BasePermission):
    def has_permission(self, request, view):
        """
        Only have permission to create the feedback if the user has permission to
        edit the associated study.
        """
        if request.method not in permissions.SAFE_METHODS:
            response = request.data.get("response")
            if response and response.get("id"):
                related_study = get_object_or_404(
                    Response, uuid=response.get("id")
                ).study
                user = request.user
                if not user.has_perm("studies.can_edit_study", related_study):
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
                child = get_object_or_404(Child, uuid=child_id.get("id"))
                if child.user != request.user:
                    return False
        return True
