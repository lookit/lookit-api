from django.utils.translation import gettext as _
from model_utils import Choices

states = [
    "created",
    "submitted",
    "rejected",
    "retracted",
    "approved",
    "active",
    "paused",
    "deactivated",
    "archived",
]

state_tuples = tuple((x, _(x.title())) for x in states)

STATE_UI_SIGNALS = {
    "created": "info",
    "submitted": "success",
    "rejected": "danger",
    "retracted": "danger",
    "approved": "success",
    "active": "success",
    "paused": "warning",
    "deactivated": "info",
    "archived": "info",
}

# Dictionary with the states for the study and tooltip text for providing additional information
STATUS_HELP_TEXT = {
    "created": "Study has not been submitted for approval",
    "active": "Study is collecting data",
    "submitted": "Study is awaiting approval",
    "draft": "Study has not been submitted for approval",
    "approved": "Study is approved but not started",
    "rejected": "Study has been rejected. Please edit before resubmitting.",
    "retracted": "Study has been withdrawn",
    "paused": "Study is not collecting data",
    "deactivated": "Study is not collecting data",
    "archived": "Study has been archived and removed from search.",
    "previewing": "Study is being built and deployed to Google Cloud Storage for previewing.",
    "deploying": "Study is being built and deployed to Google Cloud Storage",
}

STATE_CHOICES = Choices(*state_tuples)

transitions = [
    {
        "trigger": "submit",
        "source": "created",
        "dest": "submitted",
        "after": "notify_administrators_of_submission",
    },
    {
        "trigger": "approve",
        "source": "submitted",
        "dest": "approved",
        "after": "notify_submitter_of_approval",
    },
    {
        "trigger": "reject",
        "source": ["submitted", "active", "paused", "deactivated"],
        "dest": "rejected",
        "after": "notify_submitter_of_rejection",
    },
    {
        "trigger": "reject",
        "source": "approved",
        "dest": "rejected",
        "after": "notify_submitter_of_recission",
    },
    {
        "trigger": "archive",
        "source": [
            "created",
            "rejected",
            "retracted",
            "submitted",
            "approved",
            "active",
            "paused",
            "deactivated",
        ],
        "dest": "archived",
    },
    {
        "trigger": "retract",
        "source": "submitted",
        "dest": "retracted",
        "after": "notify_administrators_of_retraction",
    },
    {
        "trigger": "resubmit",
        "source": ["rejected", "retracted"],
        "dest": "submitted",
        "after": "notify_administrators_of_submission",
    },
    {
        "trigger": "activate",
        "source": ["approved", "paused"],
        "dest": "active",
        "before": ["check_if_built"],
        "after": ["notify_administrators_of_activation"],
    },
    {
        "trigger": "pause",
        "source": "active",
        "dest": "paused",
        "after": "notify_administrators_of_pause",
    },
    {
        "trigger": "deactivate",
        "source": ["active", "paused"],
        "dest": "deactivated",
        "after": "notify_administrators_of_deactivation",
    },
]

TRANSITION_HELP_TEXT = {
    "submit": "This will notify Lookit admins that your study is ready for review. If you make additional changes, you will need to resubmit.",
    "resubmit": "This will notify Lookit admins that your study is ready for review. If you make additional changes, you will need to resubmit.",
    "reject": "Your comments will be sent to study researchers and they will need to resubmit before they can begin data collection.",
    "retract": "This will retract your previous request for Lookit admin review of your study. You will need to resubmit to request review after making any additional changes.",
    "approve": "This will approve the study and allow researchers to begin data collection.",
    "activate": "This will allow participants to view and take part in your study. You should be ready to field their questions and provide compensation if offered.",
    "pause": "This will stop participants from accessing your study for now. You can re-activate your study whenever you are ready to collect data again, without requiring Lookit admin review.",
    "deactivate": "This will archive the study and prevent participants from accessing it. You will still be able to access your study data, but would need to resubmit it to collect more data. If you expect to collect more data for this study, use the Pause action instead.",
    "archive": "This will effectively delete your study! You will not be able to access your study or any response data. If you have already collected participant data or might want your study protocol for reference, deactivate instead.",
}

COMMENTS_HELP_TEXT = {
    "submit": "Please list the researchers outside your group who have provided feedback on your study prior to submission, and the changes you made in response to peer feedback. (If this is a revision to an active study, list new changes made after approval)",
    "resubmit": "Please list all changes you have made since your study was last approved. This will speed up the review process.",
    "reject": "Please list any changes that need to be made before the study can be approved.",
    "approve": "Please feel free to leave any comments here.",
}

TRANSITION_LABELS = {
    "submit": "Submit (submit study for Lookit admin review)",
    "resubmit": "Submit (submit study for Lookit admin review)",
    "reject": "Reject (request changes before researchers can collect data)",
    "retract": "Retract (retract request for Lookit admin study review)",
    "approve": "Approve (allow researchers to start data collection)",
    "activate": "Start (start data collection - make study accessible to participants)",
    "pause": "Pause (pause data collection - make study inaccessible to participants)",
    "deactivate": "Deactivate (archive study - data collection is complete)",
    "archive": "Delete (delete study and any data)",
}

DECLARATIONS = {
    "submit": {
        "issue_deception": "Deception/withholding of information",
        "issue_length": "Sessions longer than 30 minutes",
        "issue_consent": "Departures from the standard Lookit template consent form or recorded confirmation statement",
        "issue_externaldata": "Incorporation of participant information from other sources (e.g. a school ID number)",
        "issue_personaldata": "Collection of personally identifying information such as email addresses or zip codes",
        "issue_sensitive": "Sensitive topics or questions (e.g. political subjects, race, bullying, mental health)",
    }
}
