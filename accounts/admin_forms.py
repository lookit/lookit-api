from django import forms

from accounts.models import User


class SpamAdminForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ("admin_comments",)
