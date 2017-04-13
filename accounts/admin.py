from django.contrib import admin

from accounts.models import CollaboratorProfile, ParticipantProfile

from .models import User

admin.site.register(User)
admin.site.register(CollaboratorProfile)
admin.site.register(ParticipantProfile)
