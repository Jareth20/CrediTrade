from django.contrib import admin

from .models import (
    Cliente,
    DocumentoRespaldo,
    EventoTrazabilidad,
    NotaCredito,
    OrdenNegociacion,
    RegistroSimuladoTitulo,
    ReporteIA,
    SolicitudAprobacion,
    SugerenciaIA,
    ValidacionNota,
    EjecucionAgente,
    EventoAgente,
    MemoriaAgente,
    FragmentoDocumento,
)


@admin.register(Cliente)
class ClienteAdmin(admin.ModelAdmin):
    list_display = (
        "nombre_razon_social",
        "ruc_identificacion",
        "tipo_relacion",
        "estado_cuenta_sri",
        "autorizacion_consulta",
    )
    search_fields = ("nombre_razon_social", "ruc_identificacion", "representante_legal")
    list_filter = ("tipo_relacion", "estado_cuenta_sri", "autorizacion_consulta")


class DocumentoInline(admin.TabularInline):
    model = DocumentoRespaldo
    extra = 0


class EventoInline(admin.TabularInline):
    model = EventoTrazabilidad
    extra = 0
    readonly_fields = ("operador", "accion", "descripcion", "metadatos", "creado_en")
    can_delete = False


@admin.register(NotaCredito)
class NotaCreditoAdmin(admin.ModelAdmin):
    list_display = (
        "numero_titulo",
        "cliente_vendedor",
        "tipo_nota",
        "valor_nominal",
        "saldo_disponible",
        "estado_flujo",
        "actualizado_en",
    )
    list_filter = ("estado_flujo", "tipo_nota", "origen_tributario", "bloqueada")
    search_fields = (
        "numero_titulo",
        "cliente_vendedor__ruc_identificacion",
        "cliente_vendedor__nombre_razon_social",
    )
    autocomplete_fields = ("cliente_vendedor", "cliente_comprador", "recepcionista", "contador", "vendedor")
    inlines = [DocumentoInline, EventoInline]


@admin.register(RegistroSimuladoTitulo)
class RegistroSimuladoTituloAdmin(admin.ModelAdmin):
    list_display = (
        "numero_titulo",
        "titular_ruc",
        "tipo_nota",
        "saldo",
        "estado",
        "bloqueada",
    )
    search_fields = ("numero_titulo", "titular_ruc")
    list_filter = ("tipo_nota", "estado", "bloqueada")


@admin.register(ValidacionNota)
class ValidacionNotaAdmin(admin.ModelAdmin):
    list_display = ("nota", "fuente", "resultado", "existe", "bloqueada", "realizada_en")
    list_filter = ("fuente", "resultado", "existe", "bloqueada")
    readonly_fields = (
        "id", "nota", "fuente", "existe", "saldo_fuente", "estado_fuente",
        "bloqueada", "motivo_bloqueo", "campos_faltantes", "inconsistencias",
        "duplicados", "coincidencias_riesgo", "siguiente_accion",
        "explicacion_ia", "resultado", "realizada_por", "realizada_en",
        "actualizado_en", "eliminado_en", "eliminado_por", "motivo_eliminacion",
    )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


admin.site.register(SugerenciaIA)
admin.site.register(OrdenNegociacion)
admin.site.register(ReporteIA)
admin.site.register(SolicitudAprobacion)
admin.site.register(EventoTrazabilidad)
admin.site.register(EjecucionAgente)
admin.site.register(EventoAgente)
admin.site.register(MemoriaAgente)
admin.site.register(FragmentoDocumento)
