from django.contrib.admin.apps import AdminConfig


class TwoFactorAuthProtectedAdminConfig(AdminConfig):
    default_site = "project.admin.TwoFactorAuthProtectedAdminSite"
