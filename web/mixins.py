import guardian

class LoginRequiredMixin(guardian.mixins.LoginRequiredMixin):
   
   def dispatch(self, request, *args, **kwargs):
       print(request.GET)
       print('Found this %s'% request.POST.get('next',''))
       return super().dispatch(request, *args, **kwargs)
   

