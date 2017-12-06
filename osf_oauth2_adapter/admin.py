from django.contrib import admin
from allauth.socialaccount.models import SocialToken, SocialApp, SocialAccount
# Import this because auth models get registered on import.
from allauth.socialaccount.admin import SocialTokenAdmin, SocialAppAdmin, SocialAccountAdmin

admin.site.unregister(SocialToken)
admin.site.unregister(SocialAccount)
admin.site.unregister(SocialApp)
