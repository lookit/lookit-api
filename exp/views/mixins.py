from guardian.mixins import LoginRequiredMixin
from django.conf import settings

class ExperimenterLoginRequiredMixin(LoginRequiredMixin):
    login_url = settings.EXPERIMENTER_LOGIN_URL
