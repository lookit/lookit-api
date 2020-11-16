import guardian

class LoginRequiredMixin(guardian.mixins.LoginRequiredMixin):
   
   def dispatch(self, request, *args, **kwargs):
       print(request)
       return super().dispatch(request, *args, **kwargs)
   

