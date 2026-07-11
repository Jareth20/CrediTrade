from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.db import models


class Operador(AbstractUser):
    puede_recepcionar = models.BooleanField(
        default=False,
        verbose_name="Operador 1 - Recepcionista",
    )
    puede_validar = models.BooleanField(
        default=False,
        verbose_name="Operador 2 - Contador",
    )
    puede_negociar = models.BooleanField(
        default=False,
        verbose_name="Operador 3 - Vendedor",
    )
    cargo_visible = models.CharField(max_length=100, blank=True)
    activo_operativamente = models.BooleanField(default=True)

    class Meta:
        verbose_name = "operador"
        verbose_name_plural = "operadores"
        indexes = [
            models.Index(
                fields=["is_active", "activo_operativamente"],
                name="operador_activo_idx",
            )
        ]

    def clean(self):
        super().clean()
        if (
            self.activo_operativamente
            and not self.is_superuser
            and not any(
                (
                    self.puede_recepcionar,
                    self.puede_validar,
                    self.puede_negociar,
                )
            )
        ):
            raise ValidationError(
                "Un operador activo debe tener al menos un rol operativo."
            )

    def tiene_rol(self, *tipos):
        if self.is_superuser:
            return True
        permisos = {
            1: self.puede_recepcionar,
            2: self.puede_validar,
            3: self.puede_negociar,
        }
        normalizados = []
        for tipo in tipos:
            try:
                normalizados.append(int(tipo))
            except (TypeError, ValueError):
                continue
        return any(permisos.get(tipo, False) for tipo in normalizados)

    @property
    def es_recepcionista(self):
        return self.puede_recepcionar

    @property
    def es_contador(self):
        return self.puede_validar

    @property
    def es_vendedor(self):
        return self.puede_negociar

    @property
    def rol_nombre(self):
        roles = []
        if self.is_superuser:
            roles.append("Administrador")
        if self.puede_recepcionar:
            roles.append("Operador 1 - Recepcionista")
        if self.puede_validar:
            roles.append("Operador 2 - Contador")
        if self.puede_negociar:
            roles.append("Operador 3 - Vendedor")
        return " · ".join(roles) if roles else "Sin rol operativo"

    def __str__(self):
        nombre = self.get_full_name() or self.username
        return f"{nombre} ({self.rol_nombre})"
