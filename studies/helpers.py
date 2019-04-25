import logging
from datetime import datetime

from django.core.mail.message import EmailMultiAlternatives
from django.template.loader import get_template

from project.celery import app
from project.settings import BASE_URL, EMAIL_FROM_ADDRESS, OSF_URL


logger = logging.getLogger(__name__)


@app.task
def send_mail(
    template_name,
    subject,
    to_addresses,
    cc=None,
    bcc=None,
    from_email=None,
    message_uuid=None,
    **context,
):
    """
    Helper for sending templated email

    :param str template_name: Name of the template to send. There should exist a txt and html version
    :param str subject: Subject line of the email
    :param str from_address: From address for email
    :param list to_addresses: List of addresses to email. If str is provided, wrapped in list
    :param list cc: List of addresses to carbon copy
    :param list bcc: List of addresses to blind carbon copy
    :param str custom_message Custom email message - for use instead of a template
    :kwargs: Context vars for the email template
    """
    context["base_url"] = BASE_URL
    context["osf_url"] = OSF_URL

    text_content = get_template("emails/{}.txt".format(template_name)).render(context)
    html_content = get_template("emails/{}.html".format(template_name)).render(context)

    if not isinstance(to_addresses, list):
        to_addresses = [to_addresses]

    from_address = from_email or EMAIL_FROM_ADDRESS
    email = EmailMultiAlternatives(
        subject, text_content, from_address, to_addresses, cc=cc, bcc=bcc
    )
    email.attach_alternative(html_content, "text/html")
    email.send()

    if message_uuid:
        from accounts.models import Message  # Prevent circular import.

        message = Message.objects.get(uuid=message_uuid)
        message.email_sent = datetime.now()
        message.save()


class FrameActionDispatcher(object):
    """Dispatches an action based on the latest frame ID of a given response.

    The idea with this class is that it's easy to extend - you just add a method with the lower-case
    name matching the frame type you want to act on, and make sure to include the response and frame_data as
    named arguments, plus optional args/kwargs that can be passed in at call time.
    """

    def __call__(self, response, *args, **kwargs):
        """Dispatcher that delegates to inner methods."""
        if response.sequence:
            current_frame_id = response.sequence[-1]
            frame_data = response.exp_data[current_frame_id]
            frame_type = frame_data.get("frameType", None)
            if frame_type is None:
                return
        else:
            return

        try:
            return getattr(self, frame_type.lower())(
                response, frame_data, *args, **kwargs
            )
        except AttributeError as e:
            logger.warning(f"{e.args} is not registered for frame-specific action.")

    def default(self, response, frame_data: dict, *args, **kwargs):
        """Default frame hook.

        Args:
            response: Response Model.
            frame_data: dictionary of frame data.
        """
        pass

    def exit(self, response, frame_data: dict, *args, **kwargs):
        """Exit frame hook.

        Args:
            response: Response Model.
            frame_data: dictionary of frame data.
        """
        withdrawal = frame_data.get("withdrawal", None)
        if withdrawal:
            for video in response.videos.filter(is_consent_footage=False):
                video.delete(delete_in_s3=True)
        elif withdrawal is None:
            logger.warning(
                f"withdrawal property not found in exit frame for {response}"
            )
        else:  # Withdrawal is false, do nothing.
            pass

    def consent(self, response, frame_data: dict, *args, **kwargs):
        """This will eventually take over the functionality that's currently covered in the frontend."""
        pass
