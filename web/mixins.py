import guardian

class LoginRequiredMixin(guardian.mixins.LoginRequiredMixin):
   
   def dispatch(self, request, *args, **kwargs):
       print('Found this %s'% request.GET.get('next',''))
       return super().dispatch(request, *args, **kwargs)
   

