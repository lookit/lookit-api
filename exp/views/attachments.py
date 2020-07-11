from django.contrib import messages
from django.http import HttpResponseRedirect
from django.shortcuts import redirect, reverse
from django.views import generic

from exp.mixins.paginator_mixin import PaginatorMixin
from exp.views.mixins import (
    CanViewStudyResponsesMixin,
    SingleObjectParsimoniousQueryMixin,
)
from studies.models import Study
from studies.permissions import StudyPermission
from studies.tasks import build_zipfile_of_videos


class StudyAttachments(
    CanViewStudyResponsesMixin,
    PaginatorMixin,
    SingleObjectParsimoniousQueryMixin,
    generic.DetailView,
):
    """
    StudyAttachments View shows video attachments for the study
    """

    template_name = "studies/study_attachments.html"
    queryset = Study.objects.prefetch_related("responses", "videos")

    def get_consented_videos(self, study):
        """
        Fetches all consented videos this user has access to.
        TODO: use a helper (e.g. in queries) select_videos_for_user to fetch the appropriate videos here
        and in build_zipfile_of_videos - deferring for the moment to work out dependencies.
        """
        videos = study.videos_for_consented_responses
        if not self.request.user.has_study_perms(
            StudyPermission.READ_STUDY_RESPONSE_DATA, study
        ):
            videos = videos.filter(response__is_preview=True)
        if not self.request.user.has_study_perms(
            StudyPermission.READ_STUDY_PREVIEW_DATA, study
        ):
            videos = videos.filter(response__is_preview=False)
        return videos

    def get_context_data(self, **kwargs):
        """
        In addition to the study, adds several items to the context dictionary.  Study results
        are paginated.
        """
        context = super().get_context_data(**kwargs)
        orderby = self.request.GET.get("sort", "full_name")
        match = self.request.GET.get("match", "")
        videos = self.get_consented_videos(context["study"])
        if match:
            videos = videos.filter(full_name__icontains=match)
        if orderby:
            videos = videos.order_by(orderby)
        context["videos"] = videos
        context["match"] = match
        return context

    def post(self, request, *args, **kwargs):
        """
        Downloads study video
        """
        attachment_url = self.request.POST.get("attachment")
        match = self.request.GET.get("match", "")
        orderby = self.request.GET.get("sort", "id") or "id"

        if attachment_url:
            return redirect(attachment_url)

        if self.request.POST.get("all-attachments"):
            build_zipfile_of_videos.delay(
                f"{self.get_object().uuid}_all_attachments",
                self.get_object().uuid,
                orderby,
                match,
                self.request.user.uuid,
                consent_only=False,
            )
            messages.success(
                request,
                f"An archive of videos for {self.get_object().name} is being generated. You will be emailed a link when it's completed.",
            )

        if self.request.POST.get("all-consent-videos"):
            build_zipfile_of_videos.delay(
                f"{self.get_object().uuid}_all_consent",
                self.get_object().uuid,
                orderby,
                match,
                self.request.user.uuid,
                consent_only=True,
            )
            messages.success(
                request,
                f"An archive of consent videos for {self.get_object().name} is being generated. You will be emailed a link when it's completed.",
            )

        return HttpResponseRedirect(
            reverse("exp:study-attachments", kwargs=dict(pk=self.get_object().pk))
        )
