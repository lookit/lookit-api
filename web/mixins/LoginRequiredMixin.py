import guardian

class LoginRequiredMixin(guardian.mixins.LoginRequiredMixin):
    print("Hello")