import base64
from email.mime.base import MIMEBase

from django.core.mail import EmailMultiAlternatives
from sendgrid.helpers.mail import (
    Attachment,
    Category,
    Content,
    CustomArg,
    Email,
    Mail,
    Personalization,
    Substitution,
)
from sgbackend import SendGridBackend

try:
    from urllib.error import HTTPError  # pragma: no cover
except ImportError:  # pragma: no cover
    from urllib2 import HTTPError  # pragma: no cover

try:
    import rfc822
except ImportError:
    import email.utils as rfc822


class LookitSendGridBackend(SendGridBackend):
    def _build_sg_mail(self, email):
        """Custom SG email builder that handles image attachment correctly to allow inline images. """

        ############# FROM SendGridBackend._build_sg_mail: ############################################################
        mail = Mail()
        from_name, from_email = rfc822.parseaddr(email.from_email)
        # Python sendgrid client should improve
        # sendgrid/helpers/mail/mail.py:164
        if not from_name:
            from_name = None
        mail.set_from(Email(from_email, from_name))
        mail.set_subject(email.subject)

        personalization = Personalization()
        for e in email.to:
            personalization.add_to(Email(e))
        for e in email.cc:
            personalization.add_cc(Email(e))
        for e in email.bcc:
            personalization.add_bcc(Email(e))
        personalization.set_subject(email.subject)
        mail.add_content(Content("text/plain", email.body))
        if isinstance(email, EmailMultiAlternatives):
            for alt in email.alternatives:
                if alt[1] == "text/html":
                    mail.add_content(Content(alt[1], alt[0]))
        elif email.content_subtype == "html":
            mail.contents = []
            mail.add_content(Content("text/plain", " "))
            mail.add_content(Content("text/html", email.body))

        if hasattr(email, "categories"):
            for c in email.categories:
                mail.add_category(Category(c))

        if hasattr(email, "custom_args"):
            for k, v in email.custom_args.items():
                mail.add_custom_arg(CustomArg(k, v))

        if hasattr(email, "template_id"):
            mail.set_template_id(email.template_id)
            if hasattr(email, "substitutions"):
                for key, value in email.substitutions.items():
                    personalization.add_substitution(Substitution(key, value))

        # SendGrid does not support adding Reply-To as an extra
        # header, so it needs to be manually removed if it exists.
        reply_to_string = ""
        for key, value in email.extra_headers.items():
            if key.lower() == "reply-to":
                reply_to_string = value
            else:
                mail.add_header({key: value})
        # Note that if you set a "Reply-To" header *and* the reply_to
        # attribute, the header's value will be used.
        if not mail.reply_to and hasattr(email, "reply_to") and email.reply_to:
            # SendGrid only supports setting Reply-To to a single address.
            # See https://github.com/sendgrid/sendgrid-csharp/issues/339.
            reply_to_string = email.reply_to[0]
        # Determine whether reply_to contains a name and email address, or
        # just an email address.
        if reply_to_string:
            reply_to_name, reply_to_email = rfc822.parseaddr(reply_to_string)
            if reply_to_name and reply_to_email:
                mail.set_reply_to(Email(reply_to_email, reply_to_name))
            elif reply_to_email:
                mail.set_reply_to(Email(reply_to_email))

        ########################### CUSTOM  HANDLING OF ATTACHMENTS ####################################################
        for (index, attachment) in enumerate(email.attachments):
            if isinstance(attachment, MIMEBase):
                attach = Attachment()

                # Re-encode into base64 to avoid newlines; then send JSON-serializable utf-8 format.
                attach.set_content(
                    str(base64.b64encode(attachment.get_payload(decode=True)), "utf-8")
                )

                # Add Content-ID header to allow use of images via src="cid:..."
                content_id_values = attachment.get_all("Content-ID")
                if not content_id_values:
                    content_id = "attachment-%05d" % (index + 1)
                else:
                    content_id = content_id_values[0]
                attach.set_content_id(content_id)

                # Add filename, which is required by SendGrid for all attachments
                filename_values = attachment.get_all("Filename")
                if filename_values:
                    attach.set_filename(filename_values[0])
                else:
                    attach.set_filename(content_id)

                # Add Content-Disposition so we can use 'inline' to show images within body of email
                disposition_values = attachment.get_all("Content-Disposition")
                if disposition_values:
                    attach.set_disposition(disposition_values[0])

                mail.add_attachment(attach)
            elif isinstance(attachment, tuple):
                # Leave as is except assume we're using version 3+ of sgbackend
                attach = Attachment()
                attach.set_filename(attachment[0])
                base64_attachment = base64.b64encode(attachment[1])
                attach.set_content(str(base64_attachment, "utf-8"))
                attach.set_type(attachment[2])
                mail.add_attachment(attach)

        ############# FROM SendGridBackend._build_sg_mail: #############################################################
        mail.add_personalization(personalization)
        return mail.get()
