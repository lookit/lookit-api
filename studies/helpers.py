from django.core.mail.message import EmailMultiAlternatives
from django.template.loader import get_template

from project.settings import EMAIL_FROM_ADDRESS, BASE_URL


# TODO: celery taskify
def send_mail(template_name, subject, to_addresses, cc=None, bcc=None, **context):
    """
    Helper for sending templated email

    :param str template_name: Name of the template to send. There should exist a txt and html version
    :param str subject: Subject line of the email
    :param str from_address: From address for email
    :param list to_addresses: List of addresses to email. If str is provided, wrapped in list
    :param list cc: List of addresses to carbon copy
    :param list bcc: List of addresses to blind carbon copy
    :kwargs: Context vars for the email template
    """
    context['base_url'] = BASE_URL
    plain = get_template('emails/{}.txt'.format(template_name))
    html = get_template('emails/{}.html'.format(template_name))

    if not isinstance(to_addresses, list):
        to_addresses = [to_addresses]

    text_content = plain.render(context)
    html_content = html.render(context)
    email = EmailMultiAlternatives(subject, text_content, EMAIL_FROM_ADDRESS, to_addresses, cc=cc, bcc=bcc)
    email.attach_alternative(html_content, 'text/html')
    email.send()
