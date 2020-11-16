import guardian

class LoginRequiredMixin(guardian.mixins.LoginRequiredMixin):
    __metaclass__=guardian.mixins.LoginRequiredMixin
    pass