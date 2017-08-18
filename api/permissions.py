from django.shortcuts import get_object_or_404
from rest_framework import permissions

from studies.models import Response

class FeedbackPermissions(permissions.BasePermission):

    def has_permission(self, request, view):
        """
        Only have permission to create the feedback if the user has permission to
        edit the associated study.
        """
        if request.method not in permissions.SAFE_METHODS:
            response_uuid = request.data['response']['id']
            related_study = get_object_or_404(Response, uuid=response_uuid).study
            user = request.user
            if not user.has_perm('studies.can_edit_study', related_study):
                return False
        return True
