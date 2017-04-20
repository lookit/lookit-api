from django.contrib import admin

from accounts.models import Collaborator, Participant

from .models import User

admin.site.register(User)
admin.site.register(Collaborator)
admin.site.register(Participant)
