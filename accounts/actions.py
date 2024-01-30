from django.contrib import admin, messages
from django.contrib.admin import helpers
from django.template.response import TemplateResponse

from accounts import admin_forms
from accounts.models import User


@admin.action(description="Set selected as spam")
def set_selected_as_spam(modeladmin, request, queryset):
    """From a list os selected users, display each one with a comments field and
    provide an option to confirm that a user is a spammer.
    """

    # get user index from POST.  if not found then you're on the first user and
    # the index is 0.
    user_idx = int(request.POST.get("user_idx", 0))

    # If post has a value for the key "post", then we have accepted that a user
    # should be marked as spam.
    if request.POST.get("post"):
        # using the current user index, get the user's id from the list of
        # users. "_selected_action" is the list of user ids from the form.
        user_id = int(request.POST.getlist("_selected_action")[user_idx])

        # Update the current user.  Mark all "email" booleans as false, set
        # user as inactive, and set spam field to true. Additionally, add admin
        # comments from the last view's form.
        User.objects.filter(pk=user_id).update(
            is_spam=True,
            is_active=False,
            email_next_session=False,
            email_new_studies=False,
            email_study_updates=False,
            email_response_questions=False,
            admin_comments=request.POST.get("admin_comments"),
        )

        # Show success message
        modeladmin.message_user(
            request,
            f"User {request.POST.get('username', user_id)} marked as spam.",
            messages.SUCCESS,
        )

        # increment user index, as we're on to the next one.
        user_idx += 1

    if user_idx < len(queryset):
        # Parent template uses this opts.
        opts = modeladmin.model._meta
        # Current user
        user = queryset[user_idx]
        # Getting the context from modeladmin is that magic sauce that makes
        # this all work.
        context = {
            **modeladmin.admin_site.each_context(request),
            "queryset": queryset,
            "opts": opts,
            "username": user.username,
            "users": queryset,
            "user_idx": user_idx,
            "form": admin_forms.SpamAdminForm(instance=user),
            "action_checkbox_name": helpers.ACTION_CHECKBOX_NAME,
        }

        return TemplateResponse(request, "admin/set_as_spam.html", context)
