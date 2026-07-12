from decimal import Decimal

from django import forms
from django.db import models
from django.utils import timezone

from .models import (
    Cliente,
    DocumentoRespaldo,
    NotaCredito,
    OrdenNegociacion,
    ValidacionNota,
    SolicitudAprobacion,
)


class BootstrapFormMixin:
    def apply_bootstrap(self):
        for field in self.fields.values():
            widget = field.widget
            if isinstance(widget, forms.CheckboxInput):
                widget.attrs.setdefault("class", "form-check-input")
            elif isinstance(widget, forms.Select):
                widget.attrs.setdefault("class", "form-select")
            else:
                widget.attrs.setdefault("class", "form-control")
            if field.required:
                widget.attrs.setdefault("required", True)


class ClienteForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Cliente
        fields = [
            "tipo_relacion",
            "ruc_identificacion",
            "nombre_razon_social",
            "nombre_comercial",
            "representante_legal",
            "identificacion_representante",
            "correo",
            "telefono",
            "direccion",
            "estado_cuenta_sri",
            "autorizacion_consulta",
        ]
        widgets = {
            "direccion": forms.Textarea(attrs={"rows": 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.apply_bootstrap()
        self.fields["ruc_identificacion"].widget.attrs.update(
            {"inputmode": "numeric", "autocomplete": "off"}
        )

    def save(self, commit=True):
        instance = super().save(commit=False)
        if instance.autorizacion_consulta and not instance.autorizacion_fecha:
            instance.autorizacion_fecha = timezone.now()
        if commit:
            instance.save()
        return instance

    def clean_telefono(self):
        value = (self.cleaned_data.get("telefono") or "").strip()
        compact = value.replace("+", "", 1).replace(" ", "").replace("-", "")
        if value and not compact.isdigit():
            raise forms.ValidationError("Ingrese un teléfono válido; solo se permiten dígitos, +, espacios y guiones.")
        digits = "".join(char for char in value if char.isdigit())
        if value and not 7 <= len(digits) <= 15:
            raise forms.ValidationError("El teléfono debe contener entre 7 y 15 dígitos.")
        return value


class NotaCreditoForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = NotaCredito
        fields = [
            "cliente_vendedor",
            "numero_titulo",
            "tipo_nota",
            "origen_tributario",
            "valor_nominal",
            "saldo_disponible",
            "minimo_recibir",
            "fecha_emision",
            "estado_fuente",
            "observaciones_recepcion",
        ]
        widgets = {
            "fecha_emision": forms.DateInput(attrs={"type": "date"}),
            "observaciones_recepcion": forms.Textarea(attrs={"rows": 3}),
            "valor_nominal": forms.NumberInput(attrs={"step": "0.01", "min": "0"}),
            "saldo_disponible": forms.NumberInput(attrs={"step": "0.01", "min": "0"}),
            "minimo_recibir": forms.NumberInput(attrs={"step": "0.01", "min": "0"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["cliente_vendedor"].queryset = Cliente.objects.filter(
            tipo_relacion__in=[Cliente.TipoRelacion.VENDEDOR, Cliente.TipoRelacion.AMBOS]
        ).order_by("nombre_razon_social")
        self.apply_bootstrap()
        self.fields["numero_titulo"].widget.attrs.update(
            {"autocomplete": "off", "placeholder": "Ej. SIM-NCT-0001"}
        )


class DocumentoRespaldoForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = DocumentoRespaldo
        fields = [
            "tipo_documento",
            "nombre",
            "archivo_url",
            "texto_extraido",
            "fuente",
        ]
        widgets = {
            "texto_extraido": forms.Textarea(attrs={"rows": 4}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.apply_bootstrap()
        self.fields["archivo_url"].help_text = "El hash SHA-256 se genera automáticamente y no puede editarse."


class ValidacionNotaForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = ValidacionNota
        fields = ["fuente", "existe", "saldo_fuente", "estado_fuente", "bloqueada", "motivo_bloqueo", "campos_faltantes", "inconsistencias", "duplicados", "coincidencias_riesgo", "siguiente_accion", "explicacion_ia", "resultado"]
        widgets = {"explicacion_ia": forms.Textarea(attrs={"rows": 4}), "siguiente_accion": forms.Textarea(attrs={"rows": 2})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.apply_bootstrap()


class DeleteReasonForm(BootstrapFormMixin, forms.Form):
    motivo = forms.CharField(max_length=300, widget=forms.Textarea(attrs={"rows": 3}), label="Motivo de eliminación")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.apply_bootstrap()


class DecisionValidacionForm(BootstrapFormMixin, forms.Form):
    class Decision(models.TextChoices):
        APROBAR = "APROBAR", "Aprobar y pasar a negociación"
        CORREGIR = "CORREGIR", "Solicitar corrección"
        RECHAZAR = "RECHAZAR", "Rechazar caso"

    decision = forms.ChoiceField(choices=Decision.choices)
    observaciones = forms.CharField(widget=forms.Textarea(attrs={"rows": 4}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.apply_bootstrap()


class OrdenNegociacionForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = OrdenNegociacion
        fields = [
            "comprador",
            "valor_venta",
            "fecha_propuesta",
            "vigencia_hasta",
            "terminos",
            "observaciones",
        ]
        widgets = {
            "fecha_propuesta": forms.DateInput(attrs={"type": "date"}),
            "vigencia_hasta": forms.DateInput(attrs={"type": "date"}),
            "terminos": forms.Textarea(attrs={"rows": 4}),
            "observaciones": forms.Textarea(attrs={"rows": 3}),
            "valor_venta": forms.NumberInput(attrs={"step": "0.01", "min": "0"}),
        }

    def __init__(self, *args, nota=None, **kwargs):
        self.nota = nota
        super().__init__(*args, **kwargs)
        self.fields["comprador"].queryset = Cliente.objects.filter(
            tipo_relacion__in=[Cliente.TipoRelacion.COMPRADOR, Cliente.TipoRelacion.AMBOS]
        ).order_by("nombre_razon_social")
        if nota:
            self.fields["valor_venta"].help_text = (
                f"Debe estar entre ${nota.minimo_recibir:,.2f} y "
                f"${nota.saldo_disponible:,.2f}."
            )
            if not self.instance.pk:
                self.fields["valor_venta"].initial = nota.saldo_disponible
        self.apply_bootstrap()
        self.fields["terminos"].required = True

    def clean_valor_venta(self):
        value = self.cleaned_data["valor_venta"]
        if self.nota:
            if value < self.nota.minimo_recibir:
                raise forms.ValidationError("El valor es inferior al mínimo aceptado.")
            if value > self.nota.saldo_disponible:
                raise forms.ValidationError("El valor supera el saldo disponible.")
        return value

    def clean(self):
        cleaned = super().clean()
        proposal, expiry = cleaned.get("fecha_propuesta"), cleaned.get("vigencia_hasta")
        if proposal and expiry and expiry < proposal:
            self.add_error("vigencia_hasta", "La vigencia no puede ser anterior a la fecha de propuesta.")
        if len((cleaned.get("terminos") or "").strip()) < 20:
            self.add_error("terminos", "Describa los términos del contrato con al menos 20 caracteres.")
        return cleaned


class ConfirmacionPublicaForm(BootstrapFormMixin, forms.Form):
    nombre = forms.CharField(max_length=200, label="Nombre de quien confirma")
    correo = forms.EmailField(label="Correo de confirmación")
    decision = forms.ChoiceField(
        choices=[
            (SolicitudAprobacion.Estado.APROBADA, "Aprobar propuesta"),
            (SolicitudAprobacion.Estado.RECHAZADA, "Rechazar propuesta"),
        ]
    )
    comentario = forms.CharField(
        required=False, widget=forms.Textarea(attrs={"rows": 3})
    )
    declaracion = forms.BooleanField(
        label="Declaro que revisé los datos mostrados y que esta acción es una confirmación del MVP, no una transferencia o endoso ejecutado.",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.apply_bootstrap()

    def clean_nombre(self):
        value = self.cleaned_data["nombre"].strip()
        if len(value) < 3 or not any(char.isalpha() for char in value):
            raise forms.ValidationError("Ingrese el nombre completo de quien confirma.")
        return value
