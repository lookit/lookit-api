import guardian

class LoginRequiredMixin(guardian.mixins.LoginRequiredMixin):
   
   def dispatch(self, request, *args, **kwargs):
       print(self.redirect_field_name)
       print('Found this %s'% request.POST.get('next',''))
       return super().dispatch(request, *args, **kwargs)
   

