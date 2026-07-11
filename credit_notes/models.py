import uuid
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, RegexValidator
from django.db import models
from django.utils import timezone


identificacion_validator = RegexValidator(
    regex=r"^\d{10,13}$",
    message="Ingrese una cédula o RUC de 10 a 13 dígitos.",
)


class Cliente(models.Model):
    class TipoRelacion(models.TextChoices):
        COMPRADOR = "COMPRADOR", "Comprador"
        VENDEDOR = "VENDEDOR", "Vendedor"
        AMBOS = "AMBOS", "Comprador y vendedor"

    class EstadoCuentaSRI(models.TextChoices):
        ACTIVO = "ACTIVO", "Activo"
        SUSPENDIDO = "SUSPENDIDO", "Suspendido"
        PENDIENTE = "PENDIENTE", "Pendiente de consulta"
        NO_DETERMINADO = "NO_DETERMINADO", "No determinado"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tipo_relacion = models.CharField(
        max_length=12, choices=TipoRelacion.choices, db_index=True
    )
    ruc_identificacion = models.CharField(
        max_length=13,
        unique=True,
        validators=[identificacion_validator],
        db_index=True,
        verbose_name="RUC o identificación",
    )
    nombre_razon_social = models.CharField(max_length=200, db_index=True)
    nombre_comercial = models.CharField(max_length=200, blank=True)
    representante_legal = models.CharField(max_length=200, blank=True)
    identificacion_representante = models.CharField(
        max_length=13, blank=True, validators=[identificacion_validator]
    )
    correo = models.EmailField(blank=True)
    telefono = models.CharField(max_length=30, blank=True)
    direccion = models.CharField(max_length=300, blank=True)
    estado_cuenta_sri = models.CharField(
        max_length=20,
        choices=EstadoCuentaSRI.choices,
        default=EstadoCuentaSRI.PENDIENTE,
    )
    autorizacion_consulta = models.BooleanField(
        default=False,
        help_text="El cliente autorizó consultar y reutilizar información para el caso.",
    )
    autorizacion_fecha = models.DateTimeField(null=True, blank=True)
    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="clientes_creados",
    )
    creado_en = models.DateTimeField(auto_now_add=True, db_index=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["nombre_razon_social"]
        indexes = [
            models.Index(fields=["ruc_identificacion", "tipo_relacion"]),
            models.Index(fields=["creado_en"]),
        ]

    def clean(self):
        super().clean()
        self.ruc_identificacion = (self.ruc_identificacion or "").strip()
        self.nombre_razon_social = (self.nombre_razon_social or "").strip()
        if self.autorizacion_consulta and not self.autorizacion_fecha:
            self.autorizacion_fecha = timezone.now()
        if self.identificacion_representante:
            self.identificacion_representante = self.identificacion_representante.strip()

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    @property
    def puede_comprar(self):
        return self.tipo_relacion in {self.TipoRelacion.COMPRADOR, self.TipoRelacion.AMBOS}

    @property
    def puede_vender(self):
        return self.tipo_relacion in {self.TipoRelacion.VENDEDOR, self.TipoRelacion.AMBOS}

    def __str__(self):
        return f"{self.nombre_razon_social} - {self.ruc_identificacion}"


class NotaCredito(models.Model):
    class TipoNota(models.TextChoices):
        DESMATERIALIZADA_ORDINARIA = (
            "DESMATERIALIZADA_ORDINARIA",
            "Nota de crédito desmaterializada ordinaria",
        )
        ISD = "ISD", "Nota de crédito ISD"
        C4T = "C4T", "Nota de crédito proveniente de C4T"
        REINTEGRO_TRIBUTARIO = (
            "REINTEGRO_TRIBUTARIO",
            "Nota de crédito de reintegro tributario",
        )
        CARTULAR_PENDIENTE_CANJE = (
            "CARTULAR_PENDIENTE_CANJE",
            "Nota cartular pendiente de canje",
        )

    class OrigenTributario(models.TextChoices):
        PAGO_INDEBIDO = "PAGO_INDEBIDO", "Pago indebido"
        PAGO_EXCESO = "PAGO_EXCESO", "Pago en exceso"
        DEVOLUCION_IVA = "DEVOLUCION_IVA", "Devolución de IVA"
        DEVOLUCION_RENTA = "DEVOLUCION_RENTA", "Devolución de Impuesto a la Renta"
        DEVOLUCION_ISD = "DEVOLUCION_ISD", "Devolución de ISD"
        CERTIFICADO_ABONO_TRIBUTARIO = (
            "CERTIFICADO_ABONO_TRIBUTARIO",
            "Certificado de Abono Tributario",
        )
        OTRO = "OTRO", "Otro / por determinar"

    class EstadoFlujo(models.TextChoices):
        BORRADOR = "BORRADOR", "Borrador de recepción"
        PENDIENTE_VALIDACION = "PENDIENTE_VALIDACION", "Pendiente de validación"
        CORRECCION_REQUERIDA = "CORRECCION_REQUERIDA", "Corrección requerida"
        VALIDADA = "VALIDADA", "Validada por contador"
        RECHAZADA = "RECHAZADA", "Rechazada"
        EN_NEGOCIACION = "EN_NEGOCIACION", "En preparación de negociación"
        PENDIENTE_CONFIRMACIONES = (
            "PENDIENTE_CONFIRMACIONES",
            "Pendiente de confirmaciones",
        )
        LISTA_LIQUIDACION = "LISTA_LIQUIDACION", "Lista para solicitud de liquidación"
        CERRADA_DEMO = "CERRADA_DEMO", "Cierre registrado en demostración"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    numero_titulo = models.CharField(max_length=80, unique=True, db_index=True)
    cliente_vendedor = models.ForeignKey(
        Cliente,
        on_delete=models.PROTECT,
        related_name="notas_vendidas",
    )
    cliente_comprador = models.ForeignKey(
        Cliente,
        on_delete=models.PROTECT,
        related_name="notas_compradas",
        null=True,
        blank=True,
    )
    tipo_nota = models.CharField(max_length=40, choices=TipoNota.choices)
    origen_tributario = models.CharField(
        max_length=40, choices=OrigenTributario.choices
    )
    valor_nominal = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    saldo_disponible = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    minimo_recibir = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.00"))],
        help_text="Monto mínimo que el vendedor está dispuesto a recibir.",
    )
    fecha_emision = models.DateField(null=True, blank=True)
    estado_fuente = models.CharField(max_length=100, blank=True)
    bloqueada = models.BooleanField(default=False)
    motivo_bloqueo = models.CharField(max_length=300, blank=True)
    estado_flujo = models.CharField(
        max_length=35,
        choices=EstadoFlujo.choices,
        default=EstadoFlujo.BORRADOR,
        db_index=True,
    )
    observaciones_recepcion = models.TextField(blank=True)
    observaciones_validacion = models.TextField(blank=True)
    observaciones_negociacion = models.TextField(blank=True)

    recepcionista = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="notas_recepcionadas",
    )
    contador = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="notas_validadas",
        null=True,
        blank=True,
    )
    vendedor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="notas_negociadas",
        null=True,
        blank=True,
    )

    creado_en = models.DateTimeField(auto_now_add=True, db_index=True)
    actualizado_en = models.DateTimeField(auto_now=True)
    enviado_validacion_en = models.DateTimeField(null=True, blank=True)
    validado_en = models.DateTimeField(null=True, blank=True)
    iniciado_negociacion_en = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-creado_en"]
        indexes = [
            models.Index(fields=["estado_flujo", "creado_en"]),
            models.Index(fields=["cliente_vendedor", "estado_flujo"]),
            models.Index(fields=["tipo_nota", "origen_tributario"]),
        ]

    def clean(self):
        super().clean()
        self.numero_titulo = (self.numero_titulo or "").strip().upper()
        if self.saldo_disponible is not None and self.valor_nominal is not None:
            if self.saldo_disponible > self.valor_nominal:
                raise ValidationError(
                    {"saldo_disponible": "El saldo no puede superar el valor nominal."}
                )
        if self.minimo_recibir is not None and self.saldo_disponible is not None:
            if self.minimo_recibir > self.saldo_disponible:
                raise ValidationError(
                    {"minimo_recibir": "El mínimo no puede superar el saldo disponible."}
                )
        if self.cliente_vendedor_id and not self.cliente_vendedor.puede_vender:
            raise ValidationError(
                {"cliente_vendedor": "El cliente no está registrado como vendedor."}
            )
        if self.cliente_comprador_id and not self.cliente_comprador.puede_comprar:
            raise ValidationError(
                {"cliente_comprador": "El cliente no está registrado como comprador."}
            )
        for field_name, expected_type in (
            ("recepcionista", 1),
            ("contador", 2),
            ("vendedor", 3),
        ):
            operator = getattr(self, field_name, None)
            if operator and not operator.tiene_rol(expected_type):
                raise ValidationError(
                    {field_name: f"El responsable debe ser un operador tipo {expected_type}."}
                )

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    @property
    def descuento_maximo_porcentaje(self):
        if not self.saldo_disponible:
            return Decimal("0.00")
        return ((self.saldo_disponible - self.minimo_recibir) / self.saldo_disponible) * 100

    @property
    def proxima_accion(self):
        mapping = {
            self.EstadoFlujo.BORRADOR: "Completar datos, documentos y enviar a validación.",
            self.EstadoFlujo.PENDIENTE_VALIDACION: "El contador debe validar existencia, saldo y bloqueos.",
            self.EstadoFlujo.CORRECCION_REQUERIDA: "El recepcionista debe corregir y reenviar.",
            self.EstadoFlujo.VALIDADA: "El vendedor debe preparar la orden de negociación.",
            self.EstadoFlujo.RECHAZADA: "Revisar la causa del rechazo o archivar el expediente.",
            self.EstadoFlujo.EN_NEGOCIACION: "Completar comprador, valores y borrador de negociación.",
            self.EstadoFlujo.PENDIENTE_CONFIRMACIONES: "Esperar aprobación del vendedor y comprador.",
            self.EstadoFlujo.LISTA_LIQUIDACION: "Solicitar aprobación regulada de liquidación/endoso.",
            self.EstadoFlujo.CERRADA_DEMO: "Expediente cerrado en modo demostración.",
        }
        return mapping.get(self.estado_flujo, "Revisar el expediente.")

    def __str__(self):
        return f"{self.numero_titulo} - {self.cliente_vendedor.nombre_razon_social}"


class DocumentoRespaldo(models.Model):
    class TipoDocumento(models.TextChoices):
        NOTA_CREDITO = "NOTA_CREDITO", "Nota de crédito"
        AUTORIZACION = "AUTORIZACION", "Autorización del cliente"
        PODER_ENDOSO = "PODER_ENDOSO", "Poder / autorización de endoso"
        ESTADO_CUENTA = "ESTADO_CUENTA", "Estado de cuenta SRI"
        IDENTIFICACION = "IDENTIFICACION", "Identificación"
        OTRO = "OTRO", "Otro"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    nota = models.ForeignKey(
        NotaCredito, on_delete=models.CASCADE, related_name="documentos"
    )
    tipo_documento = models.CharField(max_length=30, choices=TipoDocumento.choices)
    nombre = models.CharField(max_length=200)
    archivo_url = models.URLField(
        blank=True,
        help_text="URL en Vercel Blob, S3, Supabase Storage u otro almacenamiento externo.",
    )
    texto_extraido = models.TextField(
        blank=True,
        help_text="Texto pegado o extraído para demostrar búsqueda y asistencia IA.",
    )
    hash_sha256 = models.CharField(max_length=64, blank=True)
    fuente = models.CharField(max_length=120, default="Cargado por operador")
    cargado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="documentos_cargados",
    )
    cargado_en = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-cargado_en"]
        indexes = [models.Index(fields=["nota", "tipo_documento"])]

    def clean(self):
        super().clean()
        if not self.archivo_url and not self.texto_extraido:
            raise ValidationError(
                "Incluya una URL de documento o texto extraído para el respaldo."
            )

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return self.nombre


class SugerenciaIA(models.Model):
    class Estado(models.TextChoices):
        PENDIENTE = "PENDIENTE", "Pendiente"
        ACEPTADA = "ACEPTADA", "Aceptada"
        RECHAZADA = "RECHAZADA", "Rechazada"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    nota = models.ForeignKey(
        NotaCredito, on_delete=models.CASCADE, related_name="sugerencias_ia"
    )
    campo = models.CharField(max_length=80)
    valor_actual = models.TextField(blank=True)
    valor_sugerido = models.TextField()
    confianza = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("0.50"),
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    fuente = models.CharField(max_length=160)
    evidencia = models.TextField(blank=True)
    estado = models.CharField(
        max_length=12, choices=Estado.choices, default=Estado.PENDIENTE, db_index=True
    )
    generada_por_modelo = models.CharField(max_length=80, blank=True)
    creada_en = models.DateTimeField(auto_now_add=True)
    revisada_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="sugerencias_revisadas",
        null=True,
        blank=True,
    )
    revisada_en = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["estado", "campo"]
        constraints = [
            models.UniqueConstraint(
                fields=["nota", "campo"],
                condition=models.Q(estado="PENDIENTE"),
                name="unique_pending_suggestion_per_field",
            )
        ]

    def __str__(self):
        return f"{self.nota.numero_titulo}: {self.campo}"


class RegistroSimuladoTitulo(models.Model):
    """Fuente simulada DECEVALE/SRI para demostrar validación de extremo a extremo."""

    numero_titulo = models.CharField(max_length=80, unique=True, db_index=True)
    titular_ruc = models.CharField(max_length=13, validators=[identificacion_validator])
    tipo_nota = models.CharField(max_length=40, choices=NotaCredito.TipoNota.choices)
    valor_nominal = models.DecimalField(max_digits=18, decimal_places=2)
    saldo = models.DecimalField(max_digits=18, decimal_places=2)
    estado = models.CharField(max_length=100, default="VIGENTE")
    bloqueada = models.BooleanField(default=False)
    motivo_bloqueo = models.CharField(max_length=300, blank=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "registro simulado de título"
        verbose_name_plural = "registros simulados de títulos"

    def save(self, *args, **kwargs):
        self.numero_titulo = self.numero_titulo.strip().upper()
        return super().save(*args, **kwargs)

    def __str__(self):
        return self.numero_titulo


class ValidacionNota(models.Model):
    class Fuente(models.TextChoices):
        SIMULADA = "SIMULADA", "Fuente simulada"
        CARGADA = "CARGADA", "Archivo cargado por el equipo"
        REAL = "REAL", "Integración real"

    class Resultado(models.TextChoices):
        PENDIENTE = "PENDIENTE", "Pendiente"
        CONFORME = "CONFORME", "Conforme"
        OBSERVADA = "OBSERVADA", "Observada"
        NO_CONFORME = "NO_CONFORME", "No conforme"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    nota = models.ForeignKey(
        NotaCredito, on_delete=models.CASCADE, related_name="validaciones"
    )
    fuente = models.CharField(max_length=12, choices=Fuente.choices)
    existe = models.BooleanField(default=False)
    saldo_fuente = models.DecimalField(
        max_digits=18, decimal_places=2, null=True, blank=True
    )
    estado_fuente = models.CharField(max_length=100, blank=True)
    bloqueada = models.BooleanField(default=False)
    motivo_bloqueo = models.CharField(max_length=300, blank=True)
    campos_faltantes = models.JSONField(default=list, blank=True)
    inconsistencias = models.JSONField(default=list, blank=True)
    duplicados = models.JSONField(default=list, blank=True)
    coincidencias_riesgo = models.JSONField(default=list, blank=True)
    siguiente_accion = models.CharField(max_length=300, blank=True)
    explicacion_ia = models.TextField(blank=True)
    resultado = models.CharField(
        max_length=15,
        choices=Resultado.choices,
        default=Resultado.PENDIENTE,
        db_index=True,
    )
    realizada_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="validaciones_realizadas",
    )
    realizada_en = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-realizada_en"]
        indexes = [models.Index(fields=["nota", "resultado", "realizada_en"])]

    def __str__(self):
        return f"Validación {self.nota.numero_titulo} - {self.get_resultado_display()}"


class OrdenNegociacion(models.Model):
    class Estado(models.TextChoices):
        BORRADOR = "BORRADOR", "Borrador"
        APROBADA_OPERADOR = "APROBADA_OPERADOR", "Aprobada por operador"
        ENVIADA_CONFIRMACION = "ENVIADA_CONFIRMACION", "Enviada a confirmación"
        CONFIRMADA_PARTES = "CONFIRMADA_PARTES", "Confirmada por ambas partes"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    nota = models.OneToOneField(
        NotaCredito, on_delete=models.CASCADE, related_name="orden_negociacion"
    )
    comprador = models.ForeignKey(
        Cliente, on_delete=models.PROTECT, related_name="ordenes_comprador"
    )
    valor_venta = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    porcentaje_descuento = models.DecimalField(
        max_digits=7,
        decimal_places=4,
        default=Decimal("0.0000"),
        validators=[MinValueValidator(Decimal("0.0000"))],
    )
    fecha_propuesta = models.DateField(default=timezone.localdate)
    vigencia_hasta = models.DateField(null=True, blank=True)
    terminos = models.TextField(blank=True)
    observaciones = models.TextField(blank=True)
    estado = models.CharField(
        max_length=24, choices=Estado.choices, default=Estado.BORRADOR, db_index=True
    )
    preparado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="ordenes_preparadas",
    )
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [models.Index(fields=["estado", "creado_en"])]

    def clean(self):
        super().clean()
        if self.comprador_id and not self.comprador.puede_comprar:
            raise ValidationError({"comprador": "El cliente no puede actuar como comprador."})
        if self.nota_id:
            if self.valor_venta > self.nota.saldo_disponible:
                raise ValidationError(
                    {"valor_venta": "El valor de venta no puede superar el saldo."}
                )
            if self.valor_venta < self.nota.minimo_recibir:
                raise ValidationError(
                    {"valor_venta": "El valor de venta es menor al mínimo aceptado."}
                )
        if self.preparado_por_id and not self.preparado_por.tiene_rol(3):
            raise ValidationError("La orden debe ser preparada por un operador tipo 3.")

    def save(self, *args, **kwargs):
        if self.nota_id and self.nota.saldo_disponible:
            self.porcentaje_descuento = (
                (self.nota.saldo_disponible - self.valor_venta)
                / self.nota.saldo_disponible
                * Decimal("100")
            ).quantize(Decimal("0.0001"))
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"Orden {self.nota.numero_titulo}"


class ReporteIA(models.Model):
    class Tipo(models.TextChoices):
        NEGOCIACION = "NEGOCIACION", "Ficha de negociación"
        ESTADO = "ESTADO", "Reporte de estado"
        CIERRE = "CIERRE", "Reporte de cierre"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    nota = models.ForeignKey(
        NotaCredito, on_delete=models.CASCADE, related_name="reportes_ia"
    )
    tipo = models.CharField(max_length=20, choices=Tipo.choices)
    titulo = models.CharField(max_length=200)
    resumen = models.TextField()
    contenido = models.JSONField(default=dict)
    modelo_ia = models.CharField(max_length=80, blank=True)
    generado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="reportes_generados",
    )
    generado_en = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-generado_en"]

    def __str__(self):
        return self.titulo


class SolicitudAprobacion(models.Model):
    class Parte(models.TextChoices):
        VENDEDOR = "VENDEDOR", "Vendedor inicial"
        COMPRADOR = "COMPRADOR", "Comprador"

    class Estado(models.TextChoices):
        PENDIENTE = "PENDIENTE", "Pendiente"
        APROBADA = "APROBADA", "Aprobada"
        RECHAZADA = "RECHAZADA", "Rechazada"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    orden = models.ForeignKey(
        OrdenNegociacion, on_delete=models.CASCADE, related_name="solicitudes"
    )
    parte = models.CharField(max_length=10, choices=Parte.choices)
    cliente = models.ForeignKey(
        Cliente, on_delete=models.PROTECT, related_name="solicitudes_aprobacion"
    )
    estado = models.CharField(
        max_length=10, choices=Estado.choices, default=Estado.PENDIENTE, db_index=True
    )
    confirmado_por = models.CharField(max_length=200, blank=True)
    correo_confirmacion = models.EmailField(blank=True)
    comentario = models.TextField(blank=True)
    confirmado_en = models.DateTimeField(null=True, blank=True)
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["orden", "parte"], name="unique_approval_party_per_order"
            )
        ]

    def __str__(self):
        return f"{self.get_parte_display()} - {self.orden}"


class EventoTrazabilidad(models.Model):
    id = models.BigAutoField(primary_key=True)
    nota = models.ForeignKey(
        NotaCredito, on_delete=models.CASCADE, related_name="eventos"
    )
    operador = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="eventos_trazabilidad",
    )
    accion = models.CharField(max_length=80, db_index=True)
    descripcion = models.TextField()
    metadatos = models.JSONField(default=dict, blank=True)
    creado_en = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-creado_en"]
        indexes = [models.Index(fields=["nota", "creado_en"])]

    def __str__(self):
        return f"{self.accion} - {self.nota.numero_titulo}"
