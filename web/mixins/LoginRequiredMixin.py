import guardian

class LoginRequiredMixin(guardian.mixins.LoginRequiredMixin):
    print("Hello")
    login_url='testmeplease'