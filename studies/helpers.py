from django.core.mail.message import EmailMultiAlternatives
from django.template.loader import get_template

from project.settings import EMAIL_FROM_ADDRESS, BASE_URL


# TODO: celery taskify
def send_mail(template_name, subject, to_addresses, cc=None, bcc=None, custom_message=None, from_email=None, **context):
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
    context['base_url'] = BASE_URL

    if template_name:
        text_content = get_template('emails/{}.txt'.format(template_name)).render(context)
        html_content = get_template('emails/{}.html'.format(template_name)).render(context)

    if custom_message:
        text_content = custom_message
        html_content = custom_message

    if not isinstance(to_addresses, list):
        to_addresses = [to_addresses]

    from_address = from_email or EMAIL_FROM_ADDRESS

    email = EmailMultiAlternatives(subject, text_content, from_address, to_addresses, cc=cc, bcc=bcc)
    email.attach_alternative(html_content, 'text/html')
    email.send()
