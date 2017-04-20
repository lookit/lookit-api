from django.contrib import admin

from accounts.models import Participant

from .models import User

admin.site.register(User)
admin.site.register(Participant)
