import guardian
from django.utils.translation import get_language_from_request

class LoginRequiredMixin(guardian.mixins.LoginRequiredMixin):
    # Customises guardian.mixins auth check, so that it redirects to [language-code]/login instead of just login
    def dispatch(self, request, *args, **kwargs):
        # Get language code from requested path
        lang=get_language_from_request(request, check_path=True)
        if lang:   
            # If it isn't already there, add this to the front of the login URL
            if not self.login_url[:(2+len(lang))] == ('/' + lang +'/'):
                self.login_url='/' + lang + self.login_url
        # Continue as normal
        return super().dispatch(request, *args, **kwargs)


