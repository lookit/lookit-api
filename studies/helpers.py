import copy
import logging
import re
from datetime import datetime
from email.mime.image import MIMEImage

from django.core.mail.message import EmailMultiAlternatives
from django.template.loader import get_template

from project.celery import app
from project.settings import BASE_URL, EMAIL_FROM_ADDRESS

logger = logging.getLogger(__name__)


@app.task
def send_mail(
    template_name, subject, to_addresses, cc=None, bcc=None, from_email=None, **context
):
    """
    Helper for sending templated email

    :param str template_name: Name of the template to send. There should exist a txt and html version
    :param str subject: Subject line of the email
    :param str from_email: From address for email
    :param list to_addresses: List of addresses to email. If str is provided, wrapped in list
    :param list cc: List of addresses to carbon copy
    :param list bcc: List of addresses to blind carbon copy
    :param str custom_message Custom email message - for use instead of a template
    :kwargs: Context vars for the email template
    """
    context["base_url"] = BASE_URL

    # For text version: replace images with [IMAGE] so they're not removed entirely
    context_plain_text = copy.deepcopy(context)
    IMAGE_SCHEME = re.compile(r"<img .*?>", re.MULTILINE)
    context_plain_text["custom_message"] = re.sub(
        IMAGE_SCHEME, "[IMAGE]", context_plain_text["custom_message"]
    )

    # Render into template
    text_content = get_template("emails/{}.txt".format(template_name)).render(
        context_plain_text
    )
    html_content = get_template("emails/{}.html".format(template_name)).render(context)

    if not isinstance(to_addresses, list):
        to_addresses = [to_addresses]

    from_address = from_email or EMAIL_FROM_ADDRESS
    email = EmailMultiAlternatives(
        subject, text_content, from_address, to_addresses, cc=cc, bcc=bcc
    )

    # For HTML version: Replace inline images with attachments referenced. See
    # https://gist.github.com/osantana/833045a89ccbc6fc50c1 for reference
    INLINE_SCHEME = re.compile(
        r' src="data:image/(?P<subtype>.*?);base64,(?P<path>.*?)" ?', re.MULTILINE
    )
    images_data = []

    def repl(match):
        images_data.append((match.group("subtype"), match.group("path")))
        return ' src="cid:image-%05d" ' % (len(images_data),)

    html_content = re.sub(INLINE_SCHEME, repl, html_content)

    for index, (subtype, data) in enumerate(images_data):
        image = MIMEImage(data, _subtype=subtype)
        image.add_header("Content-ID", "<image-%05d>" % (index + 1))
        email.attach(image)

    email.attach_alternative(html_content, "text/html")
    email.send()


class FrameActionDispatcher(object):
    """Dispatches an action based on the latest frame type of a given response.

    The idea with this class is that it's easy to extend - you just add a method with the lower-case
    name matching the frame type you want to act on, and make sure to include the response, frame_data,
    and current_frame_id as named arguments, plus optional args/kwargs that can be passed in at call time.
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
                response, frame_data, current_frame_id, *args, **kwargs
            )
        except AttributeError as e:
            logger.warning(f"{e.args} is not registered for frame-specific action.")

    def default(self, response, frame_data: dict, current_frame_id, *args, **kwargs):
        """Default frame hook.

        Args:
            response: Response Model.
            frame_data: dictionary of frame data.
            current_frame_id: ID of the current frame (e.g. 1-my-video-consent)
        """
        pass

    def exit(self, response, frame_data: dict, *args, **kwargs):
        """Exit frame hook.

        Args:
            response: Response Model.
            frame_data: dictionary of frame data.
            current_frame_id: ID of the current frame (e.g. 1-my-video-consent)
        """
        withdrawal = frame_data.get("withdrawal", None)
        if withdrawal:
            for video in response.videos.filter(is_consent_footage=False):
                video.delete()
        elif withdrawal is None:
            logger.warning(
                f"withdrawal property not found in exit frame for {response}"
            )
        else:  # Withdrawal is false, do nothing.
            pass

    def consent(self, response, frame_data: dict, current_frame_id, *args, **kwargs):
        """Upon saving data from a consent frame, mark the video collected as consent footage.
        This means the participant will have to proceed from the consent frame before 
        consent footage is accessible to researchers. Video model is ALSO marked as consent
        footage upon creation if exp_data already has the consent frame added. This hook
        covers the case where the Video is created first and then exp_data is updated; that
        hook covers the case where exp_data is updated before the Video model is created.
        
        Args:
            response: Response Model.
            frame_data: dictionary of frame data.
            current_frame_id: ID of the current frame (e.g. 1-my-video-consent)
        """
        for video in response.videos.filter(frame_id=current_frame_id):
            video.is_consent_footage = True
            video.save()
        # Using frame_id as likely to be most robust, even with slightly convoluted generation
        # of frame IDs during randomizer-generated frames (there should at least never be
        # duplicate frame IDs because of the incrementing frame number at the start of the
        # ID). But alternative in case needed in future is to use video filenames -
        # video.full_name includes extension (.mp4), videoList is filename w/o extension:
        #
        # if any([consentFilename in video.full_name for consentFilename in frame_data.get("videoList", [])]):
