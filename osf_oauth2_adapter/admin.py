# Import this because auth models get registered on import.
from allauth.socialaccount.admin import (SocialAccountAdmin, SocialAppAdmin,
                                         SocialTokenAdmin)
from allauth.socialaccount.models import SocialAccount, SocialApp, SocialToken
from django.contrib import admin

admin.site.unregister(SocialToken)
admin.site.unregister(SocialAccount)
admin.site.unregister(SocialApp)
