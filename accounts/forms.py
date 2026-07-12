from django.contrib.auth.forms import AuthenticationForm
from django.conf import settings


class LoginForm(AuthenticationForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if settings.DEMO_LOGIN_PREFILL:
            self.fields["username"].initial = "operador_total"
            self.fields["password"].initial = "OperadorDemo123!"
            self.fields["password"].widget.attrs["value"] = "OperadorDemo123!"
        self.fields["username"].widget.attrs.update(
            {"class": "form-control", "placeholder": "Usuario", "autofocus": True}
        )
        self.fields["password"].widget.attrs.update(
            {"class": "form-control", "placeholder": "Contraseña"}
        )
