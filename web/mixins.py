import guardian
from django.utils.translation import get_language_from_request

class LoginRequiredMixin(guardian.mixins.LoginRequiredMixin):
    # Customises guardian.mixins auth check, so that it redirects to [language code]/login instead of just login 
    def dispatch(self, request, *args, **kwargs):
        lang=get_language_from_request(request, check_path=True)
        if lang:
            print('Switching login URL from this %s'%self.login_url)
            if not self.login_url[:(2+len(lang))] == ('/' + lang +'/'):
                self.login_url='/' + lang + self.login_url
            print(' to this %s'%self.login_url)
        return super().dispatch(request, *args, **kwargs)


