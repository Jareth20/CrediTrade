from django.contrib.auth.views import LoginView, LogoutView

from .forms import LoginForm


class OperadorLoginView(LoginView):
    template_name = "accounts/login.html"
    authentication_form = LoginForm
    redirect_authenticated_user = True


class OperadorLogoutView(LogoutView):
    pass
