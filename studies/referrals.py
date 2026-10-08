"""Lab referral links.

A researcher can share a link to a public study page or lab studies page with a
referral code for one of their labs. If a visitor without an account follows it
and then signs up, the new account records which lab referred them and the link
they arrived on.
"""

import json
import uuid
from urllib.parse import urlencode

from django.core import signing

from studies.models import Lab

REFERRAL_PARAM = "ref"
REFERRAL_COOKIE = "chs_referral"
REFERRAL_COOKIE_SALT = "studies.referrals"
# Browsers cap cookie lifetimes at 400 days, so this is as long as we can keep it.
REFERRAL_COOKIE_MAX_AGE = 400 * 24 * 60 * 60
# Every researcher is added to these labs automatically, so they can't refer anyone.
EXCLUDED_REFERRAL_LAB_NAMES = ("Demo lab", "Sandbox lab")
MAX_REFERRAL_URL_LENGTH = 2000


def referral_code(lab: Lab) -> str:
    """The code used in referral links: the lab's slug if it has one, else its UUID."""
    return lab.slug or str(lab.uuid)


def lab_for_referral_code(code: str):
    """Return the lab for a referral code, or None if it doesn't match an eligible lab."""
    if not code:
        return None
    labs = Lab.objects.exclude(name__in=EXCLUDED_REFERRAL_LAB_NAMES)
    lab = labs.filter(slug=code).first()
    if lab is None:
        try:
            lab = labs.filter(uuid=uuid.UUID(code)).first()
        except ValueError:
            return None
    return lab


def referral_links(request, path: str, preferred_lab=None):
    """Referral links to `path` for each eligible lab the current user belongs to.

    Returns a list of {"lab": Lab, "url": str}, with `preferred_lab` first if the
    user is a member of it.
    """
    labs = list(
        request.user.labs.exclude(name__in=EXCLUDED_REFERRAL_LAB_NAMES).order_by("name")
    )
    if preferred_lab in labs:
        labs.remove(preferred_lab)
        labs.insert(0, preferred_lab)
    base_url = request.build_absolute_uri(path)
    return [
        {
            "lab": lab,
            "url": f"{base_url}?{urlencode({REFERRAL_PARAM: referral_code(lab)})}",
        }
        for lab in labs
    ]


def set_referral_cookie(response, lab: Lab, url: str) -> None:
    value = json.dumps({"lab": str(lab.uuid), "url": url[:MAX_REFERRAL_URL_LENGTH]})
    response.set_signed_cookie(
        REFERRAL_COOKIE,
        value,
        salt=REFERRAL_COOKIE_SALT,
        max_age=REFERRAL_COOKIE_MAX_AGE,
        secure=True,
        httponly=True,
        samesite="Lax",
    )


def get_referral(request):
    """Return (lab, url) from the referral cookie, or None if missing or invalid."""
    try:
        value = request.get_signed_cookie(
            REFERRAL_COOKIE,
            salt=REFERRAL_COOKIE_SALT,
            max_age=REFERRAL_COOKIE_MAX_AGE,
        )
        data = json.loads(value)
        lab_uuid = uuid.UUID(data["lab"])
        url = str(data.get("url", ""))[:MAX_REFERRAL_URL_LENGTH]
    except (KeyError, ValueError, TypeError, signing.BadSignature):
        return None
    lab = (
        Lab.objects.exclude(name__in=EXCLUDED_REFERRAL_LAB_NAMES)
        .filter(uuid=lab_uuid)
        .first()
    )
    if lab is None:
        return None
    return lab, url


def delete_referral_cookie(response) -> None:
    response.delete_cookie(REFERRAL_COOKIE, samesite="Lax")


class ReferralCookieMiddleware:
    """Remember the referring lab when a logged-out visitor arrives with ?ref=<code>.

    The most recent referral link wins: a new valid code replaces any earlier one.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        code = request.GET.get(REFERRAL_PARAM)
        if code and request.method == "GET" and not request.user.is_authenticated:
            lab = lab_for_referral_code(code)
            if lab is not None:
                set_referral_cookie(response, lab, request.build_absolute_uri())
        return response
