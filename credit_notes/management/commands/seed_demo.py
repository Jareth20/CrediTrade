import os
from datetime import date, timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.utils import timezone

from accounts.models import Operador
from credit_notes.models import (
    Cliente,
    DocumentoRespaldo,
    NotaCredito,
    RegistroSimuladoTitulo,
)
from credit_notes.services import registrar_evento


class Command(BaseCommand):
    help = "Crea operadores y datos demostrativos idempotentes."

    def handle(self, *args, **options):
        admin_password = os.getenv("DEMO_ADMIN_PASSWORD", "AdminDemo123!")
        operator_password = os.getenv("DEMO_OPERATOR_PASSWORD", "OperadorDemo123!")

        admin, _ = Operador.objects.get_or_create(
            username="admin",
            defaults={
                "email": "admin@example.com",
                "is_staff": True,
                "is_superuser": True,
            },
        )
        admin.is_staff = True
        admin.is_superuser = True
        admin.activo_operativamente = True
        admin.set_password(admin_password)
        admin.save()

        operators = {}
        definitions = [
            (
                "recepcionista",
                {"puede_recepcionar": True, "puede_validar": False, "puede_negociar": False},
                "Rosa",
                "Recepción",
            ),
            (
                "contador",
                {"puede_recepcionar": False, "puede_validar": True, "puede_negociar": False},
                "Carlos",
                "Cumplimiento",
            ),
            (
                "vendedor",
                {"puede_recepcionar": False, "puede_validar": False, "puede_negociar": True},
                "Valeria",
                "Negociación",
            ),
            (
                "operador_total",
                {"puede_recepcionar": True, "puede_validar": True, "puede_negociar": True},
                "Alex",
                "Operador integral",
            ),
        ]
        for username, permisos, first_name, cargo in definitions:
            user, _ = Operador.objects.get_or_create(
                username=username,
                defaults={
                    "first_name": first_name,
                    "last_name": "Demo",
                    "email": f"{username}@example.com",
                    "cargo_visible": cargo,
                },
            )
            user.first_name = first_name
            user.last_name = "Demo"
            user.cargo_visible = cargo
            user.activo_operativamente = True
            user.puede_recepcionar = permisos["puede_recepcionar"]
            user.puede_validar = permisos["puede_validar"]
            user.puede_negociar = permisos["puede_negociar"]
            user.set_password(operator_password)
            user.save()
            operators[username] = user

        seller, _ = Cliente.objects.get_or_create(
            ruc_identificacion="0999999999001",
            defaults={
                "tipo_relacion": Cliente.TipoRelacion.VENDEDOR,
                "nombre_razon_social": "Exportadora Andina Demo S.A.",
                "nombre_comercial": "Andina Demo",
                "representante_legal": "Ana Pérez",
                "identificacion_representante": "0912345678",
                "correo": "ana@example.com",
                "telefono": "0990000000",
                "direccion": "Guayaquil, Ecuador",
                "estado_cuenta_sri": Cliente.EstadoCuentaSRI.ACTIVO,
                "autorizacion_consulta": True,
                "autorizacion_fecha": timezone.now(),
                "creado_por": operators["recepcionista"],
            },
        )
        buyer, _ = Cliente.objects.get_or_create(
            ruc_identificacion="0999999998001",
            defaults={
                "tipo_relacion": Cliente.TipoRelacion.COMPRADOR,
                "nombre_razon_social": "Inversiones Pacífico Demo C.A.",
                "representante_legal": "Luis Gómez",
                "correo": "luis@example.com",
                "estado_cuenta_sri": Cliente.EstadoCuentaSRI.ACTIVO,
                "autorizacion_consulta": True,
                "autorizacion_fecha": timezone.now(),
                "creado_por": operators["vendedor"],
            },
        )

        historic, created = NotaCredito.objects.get_or_create(
            numero_titulo="SIM-NCT-HIST-0001",
            defaults={
                "cliente_vendedor": seller,
                "tipo_nota": NotaCredito.TipoNota.REINTEGRO_TRIBUTARIO,
                "origen_tributario": NotaCredito.OrigenTributario.DEVOLUCION_IVA,
                "valor_nominal": Decimal("12500.00"),
                "saldo_disponible": Decimal("12500.00"),
                "minimo_recibir": Decimal("11875.00"),
                "fecha_emision": date.today() - timedelta(days=90),
                "estado_fuente": "VIGENTE",
                "estado_flujo": NotaCredito.EstadoFlujo.CERRADA_DEMO,
                "recepcionista": operators["recepcionista"],
                "contador": operators["contador"],
                "vendedor": operators["vendedor"],
                "cliente_comprador": buyer,
            },
        )
        if created:
            registrar_evento(
                historic,
                operators["recepcionista"],
                "CASO_HISTORICO_CREADO",
                "Antecedente demo para reutilización de datos.",
            )

        note, created = NotaCredito.objects.get_or_create(
            numero_titulo="SIM-NCT-0001",
            defaults={
                "cliente_vendedor": seller,
                "tipo_nota": NotaCredito.TipoNota.REINTEGRO_TRIBUTARIO,
                "origen_tributario": NotaCredito.OrigenTributario.DEVOLUCION_IVA,
                "valor_nominal": Decimal("25000.00"),
                "saldo_disponible": Decimal("24500.00"),
                "minimo_recibir": Decimal("23275.00"),
                "fecha_emision": date.today() - timedelta(days=10),
                "estado_fuente": "PENDIENTE DE VALIDACIÓN",
                "estado_flujo": NotaCredito.EstadoFlujo.BORRADOR,
                "recepcionista": operators["recepcionista"],
                "observaciones_recepcion": "Caso principal para demostrar el flujo de extremo a extremo.",
            },
        )
        if created:
            DocumentoRespaldo.objects.create(
                nota=note,
                tipo_documento=DocumentoRespaldo.TipoDocumento.NOTA_CREDITO,
                nombre="Nota de crédito simulada",
                texto_extraido=(
                    "Título SIM-NCT-0001. Titular 0999999999001. "
                    "Valor nominal 25000.00. Saldo disponible 24500.00."
                ),
                fuente="Archivo ficticio del hackathon",
                cargado_por=operators["recepcionista"],
            )
            registrar_evento(
                note,
                operators["recepcionista"],
                "CASO_CREADO",
                "Caso demo creado en recepción.",
            )

        RegistroSimuladoTitulo.objects.update_or_create(
            numero_titulo="SIM-NCT-0001",
            defaults={
                "titular_ruc": seller.ruc_identificacion,
                "tipo_nota": NotaCredito.TipoNota.REINTEGRO_TRIBUTARIO,
                "valor_nominal": Decimal("25000.00"),
                "saldo": Decimal("24500.00"),
                "estado": "VIGENTE",
                "bloqueada": False,
            },
        )

        self.stdout.write(self.style.SUCCESS("Datos demo creados/actualizados."))
        self.stdout.write("Usuarios:")
        self.stdout.write(f"  admin / {admin_password}")
        self.stdout.write(f"  recepcionista / {operator_password}")
        self.stdout.write(f"  contador / {operator_password}")
        self.stdout.write(f"  vendedor / {operator_password}")
        self.stdout.write(f"  operador_total / {operator_password}")
