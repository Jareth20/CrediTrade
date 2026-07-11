from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import Operador


@admin.register(Operador)
class OperadorAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (
        (
            "Roles operativos",
            {
                "fields": (
                    "puede_recepcionar",
                    "puede_validar",
                    "puede_negociar",
                    "cargo_visible",
                    "activo_operativamente",
                )
            },
        ),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        (
            "Roles operativos",
            {
                "fields": (
                    "puede_recepcionar",
                    "puede_validar",
                    "puede_negociar",
                    "cargo_visible",
                    "activo_operativamente",
                )
            },
        ),
    )
    list_display = (
        "username",
        "email",
        "rol_nombre",
        "activo_operativamente",
        "is_staff",
    )
    list_filter = (
        "puede_recepcionar",
        "puede_validar",
        "puede_negociar",
        "activo_operativamente",
        "is_staff",
        "is_active",
    )
