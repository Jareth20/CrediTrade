from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect


def role_required(*allowed_types):
    def decorator(view_func):
        @login_required
        @wraps(view_func)
        def wrapped(request, *args, **kwargs):
            user = request.user
            if not getattr(user, "activo_operativamente", False):
                messages.error(request, "Tu usuario no está habilitado operativamente.")
                return redirect("accounts:logout")
            if user.tiene_rol(*allowed_types):
                return view_func(request, *args, **kwargs)
            messages.error(request, "No tienes permiso para acceder a este módulo.")
            return redirect("dashboard")

        return wrapped

    return decorator
