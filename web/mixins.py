import guardian
from django.utils.translation import get_language_from_request

class LoginRequiredMixin(guardian.mixins.LoginRequiredMixin):
    # Customises guardian.mixins auth check, so that it redirects to [language code]/login instead of just login 
    def dispatch(self, request, *args, **kwargs):
        print(request.path)
        print(get_language_from_request(request, check_path=True))
        print('Found this %s'% request.POST.get('next',''))
        return super().dispatch(request, *args, **kwargs)


