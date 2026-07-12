from datetime import date
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.core.exceptions import ValidationError
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError, transaction
from django.db.models import Count, Q
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.views.decorators.http import require_GET, require_POST

from .ai_services import (
    GeminiServiceError,
    generar_explicacion_validacion,
    generar_reporte_negociacion,
    generar_sugerencias_nota,
)
from .decorators import role_required
from .forms import (
    ClienteForm,
    ConfirmacionPublicaForm,
    DecisionValidacionForm,
    DocumentoRespaldoForm,
    NotaCreditoForm,
    OrdenNegociacionForm,
    ValidacionNotaForm,
    DeleteReasonForm,
)
from .models import (
    Cliente,
    DocumentoRespaldo,
    EventoTrazabilidad,
    NotaCredito,
    OrdenNegociacion,
    ReporteIA,
    SolicitudAprobacion,
    SugerenciaIA,
    ValidacionNota,
    OperacionIdempotente,
)
from .pdf_reports import build_negotiation_pdf
from .services import (
    buscar_antecedentes,
    enviar_a_validacion,
    ejecutar_validacion_simulada,
    registrar_evento,
)


def _can_view_note(user, note):
    return user.is_authenticated and user.activo_operativamente


def _get_note_for_user(user, pk):
    note = get_object_or_404(
        NotaCredito.objects.select_related(
            "cliente_vendedor",
            "cliente_comprador",
            "recepcionista",
            "contador",
            "vendedor",
        ),
        pk=pk, eliminado_en__isnull=True,
    )
    if not _can_view_note(user, note):
        raise Http404
    return note


@login_required
def dashboard(request):
    user = request.user
    base = NotaCredito.objects.filter(eliminado_en__isnull=True)
    context = {
        "total_notas": base.count(),
        "total_clientes": Cliente.objects.filter(eliminado_en__isnull=True).count(),
        "pendientes_validacion": base.filter(
            estado_flujo=NotaCredito.EstadoFlujo.PENDIENTE_VALIDACION
        ).count(),
        "listas_negociacion": base.filter(
            estado_flujo=NotaCredito.EstadoFlujo.VALIDADA
        ).count(),
        "pendientes_confirmacion": base.filter(
            estado_flujo=NotaCredito.EstadoFlujo.PENDIENTE_CONFIRMACIONES
        ).count(),
        "recientes": base.select_related("cliente_vendedor")[:8],
    }
    if user.is_superuser:
        context["mis_casos"] = base.count()
    else:
        asignaciones = Q()
        if user.tiene_rol(1):
            asignaciones |= Q(recepcionista=user)
        if user.tiene_rol(2):
            asignaciones |= Q(contador=user)
        if user.tiene_rol(3):
            asignaciones |= Q(vendedor=user)
        context["mis_casos"] = (
            base.filter(asignaciones).distinct().count() if asignaciones else 0
        )
    return render(request, "credit_notes/dashboard.html", context)


@login_required
def cliente_list(request):
    query = request.GET.get("q", "").strip()
    clients = Cliente.objects.filter(eliminado_en__isnull=True).select_related("creado_por")
    if query:
        clients = clients.filter(
            Q(ruc_identificacion__icontains=query)
            | Q(nombre_razon_social__icontains=query)
            | Q(nombre_comercial__icontains=query)
        )
    return render(
        request,
        "credit_notes/cliente_list.html",
        {"clientes": clients[:100], "query": query},
    )


@role_required(1, 3)
def cliente_create(request):
    if request.method == "POST":
        form = ClienteForm(request.POST)
        if form.is_valid():
            client = form.save(commit=False)
            client.creado_por = request.user
            client.save()
            messages.success(request, "Cliente registrado correctamente.")
            return redirect("cliente_detail", pk=client.pk)
    else:
        form = ClienteForm()
    return render(request, "credit_notes/form.html", {"form": form, "titulo": "Registrar cliente"})


@login_required
def cliente_detail(request, pk):
    client = get_object_or_404(Cliente, pk=pk, eliminado_en__isnull=True)
    notes = NotaCredito.objects.filter(eliminado_en__isnull=True).filter(
        Q(cliente_vendedor=client) | Q(cliente_comprador=client)
    ).select_related("cliente_vendedor", "cliente_comprador")[:30]
    return render(
        request,
        "credit_notes/cliente_detail.html",
        {"cliente": client, "notas": notes},
    )


@login_required
def nota_list(request):
    state = request.GET.get("estado", "").strip()
    query = request.GET.get("q", "").strip()
    notes = NotaCredito.objects.filter(eliminado_en__isnull=True).select_related(
        "cliente_vendedor", "recepcionista", "contador", "vendedor"
    )
    if state:
        notes = notes.filter(estado_flujo=state)
    if query:
        notes = notes.filter(
            Q(numero_titulo__icontains=query)
            | Q(cliente_vendedor__ruc_identificacion__icontains=query)
            | Q(cliente_vendedor__nombre_razon_social__icontains=query)
        )
    return render(
        request,
        "credit_notes/nota_list.html",
        {
            "notas": notes[:150],
            "estados": NotaCredito.EstadoFlujo.choices,
            "estado": state,
            "query": query,
        },
    )


@role_required(1)
def nota_create(request):
    if request.method == "POST":
        form = NotaCreditoForm(request.POST)
        if form.is_valid():
            note = form.save(commit=False)
            note.recepcionista = request.user
            note.estado_flujo = NotaCredito.EstadoFlujo.BORRADOR
            note.save()
            registrar_evento(
                note,
                request.user,
                "CASO_CREADO",
                "El recepcionista creó el expediente como borrador.",
            )
            messages.success(
                request,
                "Borrador creado. Adjunta respaldo y revisa sugerencias antes de enviarlo.",
            )
            return redirect("nota_detail", pk=note.pk)
    else:
        form = NotaCreditoForm()
    return render(
        request,
        "credit_notes/nota_form.html",
        {"form": form, "titulo": "Ingreso asistido de nota de crédito"},
    )


@role_required(1)
def nota_edit(request, pk):
    note = _get_note_for_user(request.user, pk)
    if note.estado_flujo not in {
        NotaCredito.EstadoFlujo.BORRADOR,
        NotaCredito.EstadoFlujo.CORRECCION_REQUERIDA,
    }:
        messages.error(request, "La nota ya no puede editarse desde recepción.")
        return redirect("nota_detail", pk=note.pk)
    if request.method == "POST":
        form = NotaCreditoForm(request.POST, instance=note)
        if form.is_valid():
            form.save()
            registrar_evento(
                note,
                request.user,
                "DATOS_EDITADOS",
                "El recepcionista actualizó datos del expediente.",
            )
            messages.success(request, "Datos actualizados.")
            return redirect("nota_detail", pk=note.pk)
    else:
        form = NotaCreditoForm(instance=note)
    return render(
        request,
        "credit_notes/nota_form.html",
        {"form": form, "titulo": f"Editar {note.numero_titulo}", "nota": note},
    )


@login_required
def nota_detail(request, pk):
    note = _get_note_for_user(request.user, pk)
    latest_validation = note.validaciones.filter(eliminado_en__isnull=True).first()
    pending_suggestions = note.sugerencias_ia.filter(
        estado=SugerenciaIA.Estado.PENDIENTE
    ).count()
    order = getattr(note, "orden_negociacion", None)
    if order and order.eliminado_en:
        order = None
    return render(
        request,
        "credit_notes/nota_detail.html",
        {
            "nota": note,
            "latest_validation": latest_validation,
            "pending_suggestions": pending_suggestions,
            "orden": order,
            "eventos": note.eventos.select_related("operador")[:30],
            "reportes": note.reportes_ia.all()[:10],
        },
    )


@role_required(1, 2)
def documento_add(request, pk):
    note = _get_note_for_user(request.user, pk)
    if request.method == "POST":
        form = DocumentoRespaldoForm(request.POST)
        if form.is_valid():
            doc = form.save(commit=False)
            doc.nota = note
            doc.cargado_por = request.user
            doc.save()
            registrar_evento(
                note,
                request.user,
                "DOCUMENTO_AGREGADO",
                f"Se agregó el respaldo: {doc.nombre}.",
                {"tipo": doc.tipo_documento, "fuente": doc.fuente},
            )
            messages.success(request, "Documento de respaldo agregado.")
            return redirect("nota_detail", pk=note.pk)
    else:
        form = DocumentoRespaldoForm()
    return render(
        request,
        "credit_notes/form.html",
        {"form": form, "titulo": f"Agregar respaldo a {note.numero_titulo}", "nota": note},
    )


def _soft_delete(instance, user, reason):
    instance.eliminado_en = timezone.now()
    instance.eliminado_por = user
    instance.motivo_eliminacion = reason
    instance.save(update_fields=["eliminado_en", "eliminado_por", "motivo_eliminacion"])


def _delete_view(request, instance, title, redirect_name, note=None):
    form = DeleteReasonForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            _soft_delete(instance, request.user, form.cleaned_data["motivo"])
            if note:
                registrar_evento(note, request.user, "REGISTRO_ELIMINADO", f"{title} eliminado lógicamente.", {"tipo": instance._meta.model_name, "id": str(instance.pk), "motivo": form.cleaned_data["motivo"]})
        messages.success(request, "Registro eliminado con trazabilidad; el historial fue conservado.")
        return redirect(redirect_name, **({"pk": note.pk} if note and redirect_name == "nota_detail" else {}))
    return render(request, "credit_notes/confirm_delete.html", {"form": form, "titulo": title, "objeto": instance})


@role_required(1, 3)
def cliente_edit(request, pk):
    client = get_object_or_404(Cliente, pk=pk, eliminado_en__isnull=True)
    form = ClienteForm(request.POST or None, instance=client)
    if request.method == "POST" and form.is_valid():
        form.save(); messages.success(request, "Cliente actualizado.")
        return redirect("cliente_detail", pk=client.pk)
    return render(request, "credit_notes/form.html", {"form": form, "titulo": "Editar cliente"})


@role_required(1, 3)
def cliente_delete(request, pk):
    client = get_object_or_404(Cliente, pk=pk, eliminado_en__isnull=True)
    return _delete_view(request, client, "Eliminar cliente", "cliente_list")


@role_required(1)
def nota_delete(request, pk):
    note = _get_note_for_user(request.user, pk)
    return _delete_view(request, note, "Eliminar expediente", "nota_list")


@role_required(1)
@require_POST
def nota_submit_validation(request, pk):
    note = _get_note_for_user(request.user, pk)
    try:
        enviar_a_validacion(note, request.user)
        messages.success(request, "Caso enviado al módulo del contador.")
    except ValueError as exc:
        messages.error(request, str(exc))
    return redirect("nota_detail", pk=note.pk)


@role_required(1)
def antecedentes(request):
    query = request.GET.get("q", "").strip()
    notes = buscar_antecedentes(query) if query else NotaCredito.objects.none()
    return render(
        request,
        "credit_notes/antecedentes.html",
        {"notas": notes, "query": query},
    )


@role_required(1)
@require_POST
def ai_generate_suggestions(request, pk):
    note = _get_note_for_user(request.user, pk)
    if note.estado_flujo not in {
        NotaCredito.EstadoFlujo.BORRADOR,
        NotaCredito.EstadoFlujo.CORRECCION_REQUERIDA,
    }:
        messages.error(request, "Solo se generan sugerencias durante recepción/corrección.")
        return redirect("nota_detail", pk=note.pk)
    key = f"sugerencias:{note.pk}:{note.actualizado_en.isoformat()}"
    try:
        OperacionIdempotente.objects.create(clave=key, tipo="SUGERENCIAS_IA")
    except IntegrityError:
        messages.info(request, "Esta solicitud ya fue procesada o continúa en curso. No se duplicarán datos.")
        return redirect("suggestion_review", pk=note.pk)
    try:
        created = generar_sugerencias_nota(note, request.user)
    except GeminiServiceError as exc:
        OperacionIdempotente.objects.filter(clave=key, completada_en__isnull=True).delete()
        messages.error(request, str(exc))
        return redirect("nota_detail", pk=note.pk)
    OperacionIdempotente.objects.filter(clave=key).update(completada_en=timezone.now())

    if created:
        messages.success(
            request, f"Gemini generó {len(created)} sugerencias para revisar."
        )
    else:
        messages.info(
            request, "Gemini no encontró sugerencias suficientemente respaldadas."
        )
    return redirect("suggestion_review", pk=note.pk)


@role_required(1)
def suggestion_review(request, pk):
    note = _get_note_for_user(request.user, pk)
    suggestions = note.sugerencias_ia.all()
    return render(
        request,
        "credit_notes/suggestion_review.html",
        {"nota": note, "sugerencias": suggestions},
    )


def _coerce_suggestion(note, field, value):
    if field in {"valor_nominal", "saldo_disponible", "minimo_recibir"}:
        try:
            return Decimal(value)
        except InvalidOperation as exc:
            raise ValueError("El valor sugerido no es un número válido.") from exc
    if field == "fecha_emision":
        parsed = parse_date(value)
        if not parsed:
            raise ValueError("La fecha sugerida no tiene formato YYYY-MM-DD.")
        return parsed
    if field == "tipo_nota" and value not in NotaCredito.TipoNota.values:
        raise ValueError("El tipo de nota sugerido no es válido.")
    if field == "origen_tributario" and value not in NotaCredito.OrigenTributario.values:
        raise ValueError("El origen tributario sugerido no es válido.")
    return value


@role_required(1)
@require_POST
def suggestion_accept(request, suggestion_id):
    suggestion = get_object_or_404(
        SugerenciaIA.objects.select_related("nota"), pk=suggestion_id
    )
    note = suggestion.nota
    if suggestion.estado != SugerenciaIA.Estado.PENDIENTE:
        messages.info(request, "La sugerencia ya fue revisada.")
        return redirect("suggestion_review", pk=note.pk)
    if suggestion.campo not in {
        "tipo_nota",
        "origen_tributario",
        "valor_nominal",
        "saldo_disponible",
        "minimo_recibir",
        "fecha_emision",
        "estado_fuente",
    }:
        messages.error(request, "Campo de sugerencia no permitido.")
        return redirect("suggestion_review", pk=note.pk)
    try:
        with transaction.atomic():
            converted = _coerce_suggestion(note, suggestion.campo, suggestion.valor_sugerido)
            setattr(note, suggestion.campo, converted)
            note.save()
            suggestion.estado = SugerenciaIA.Estado.ACEPTADA
            suggestion.revisada_por = request.user
            suggestion.revisada_en = timezone.now()
            suggestion.save(update_fields=["estado", "revisada_por", "revisada_en"])
            registrar_evento(
                note,
                request.user,
                "SUGERENCIA_ACEPTADA",
                f"Se aceptó la sugerencia para {suggestion.campo}.",
                {"valor": suggestion.valor_sugerido, "fuente": suggestion.fuente},
            )
        messages.success(request, "Sugerencia aplicada y registrada.")
    except (ValueError, ValidationError) as exc:
        messages.error(request, f"No se pudo aplicar la sugerencia: {exc}")
    except Exception:
        messages.error(request, "No se pudo aplicar la sugerencia por un error interno.")
    return redirect("suggestion_review", pk=note.pk)


@role_required(1)
@require_POST
def suggestion_reject(request, suggestion_id):
    suggestion = get_object_or_404(
        SugerenciaIA.objects.select_related("nota"), pk=suggestion_id
    )
    if suggestion.estado == SugerenciaIA.Estado.PENDIENTE:
        suggestion.estado = SugerenciaIA.Estado.RECHAZADA
        suggestion.revisada_por = request.user
        suggestion.revisada_en = timezone.now()
        suggestion.save(update_fields=["estado", "revisada_por", "revisada_en"])
        registrar_evento(
            suggestion.nota,
            request.user,
            "SUGERENCIA_RECHAZADA",
            f"Se rechazó la sugerencia para {suggestion.campo}.",
            {"valor": suggestion.valor_sugerido, "fuente": suggestion.fuente},
        )
        messages.success(request, "Sugerencia rechazada.")
    return redirect("suggestion_review", pk=suggestion.nota.pk)


@role_required(2)
def validation_queue(request):
    notes = NotaCredito.objects.filter(eliminado_en__isnull=True).filter(
        estado_flujo=NotaCredito.EstadoFlujo.PENDIENTE_VALIDACION
    ).select_related("cliente_vendedor", "recepcionista")
    return render(request, "credit_notes/validation_queue.html", {"notas": notes})


@role_required(2)
def validation_detail(request, pk):
    note = _get_note_for_user(request.user, pk)
    if note.estado_flujo != NotaCredito.EstadoFlujo.PENDIENTE_VALIDACION:
        messages.warning(request, "El caso no está pendiente de validación.")
    validation = note.validaciones.filter(eliminado_en__isnull=True).first()
    form = DecisionValidacionForm()
    return render(
        request,
        "credit_notes/validation_detail.html",
        {"nota": note, "validacion": validation, "form": form},
    )


@role_required(2)
@require_POST
def validation_run(request, pk):
    note = _get_note_for_user(request.user, pk)
    if note.estado_flujo != NotaCredito.EstadoFlujo.PENDIENTE_VALIDACION:
        messages.error(request, "El caso no está disponible para validación.")
        return redirect("nota_detail", pk=note.pk)
    key = f"validacion:{note.pk}:{note.actualizado_en.isoformat()}"
    try:
        OperacionIdempotente.objects.create(clave=key, tipo="VALIDACION_IA")
    except IntegrityError:
        messages.info(request, "La validación ya fue solicitada. Se muestra el resultado existente.")
        return redirect("validation_detail", pk=note.pk)
    validation = ejecutar_validacion_simulada(note, request.user)
    try:
        generar_explicacion_validacion(validation)
        messages.success(
            request, "Validación comparativa ejecutada y explicada por Gemini."
        )
    except GeminiServiceError as exc:
        messages.warning(
            request,
            "La validación por reglas quedó registrada, pero Gemini no generó "
            f"la explicación: {exc}",
        )
    OperacionIdempotente.objects.filter(clave=key).update(completada_en=timezone.now(), resultado_id=str(validation.pk))
    return redirect("validation_detail", pk=note.pk)


@role_required(2)
def validation_edit(request, validation_id):
    validation = get_object_or_404(ValidacionNota, pk=validation_id, eliminado_en__isnull=True)
    note = _get_note_for_user(request.user, validation.nota_id)
    form = ValidacionNotaForm(request.POST or None, instance=validation)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            form.save()
            registrar_evento(note, request.user, "VALIDACION_EDITADA", "El contador actualizó una validación.", {"validacion": str(validation.pk)})
        messages.success(request, "Validación actualizada con trazabilidad.")
        return redirect("validation_detail", pk=note.pk)
    return render(request, "credit_notes/form.html", {"form": form, "titulo": "Editar validación", "nota": note})


@role_required(2)
def validation_delete(request, validation_id):
    validation = get_object_or_404(ValidacionNota, pk=validation_id, eliminado_en__isnull=True)
    note = _get_note_for_user(request.user, validation.nota_id)
    return _delete_view(request, validation, "Eliminar validación", "nota_detail", note)


@role_required(2)
@require_POST
def validation_decide(request, pk):
    note = _get_note_for_user(request.user, pk)
    if note.estado_flujo != NotaCredito.EstadoFlujo.PENDIENTE_VALIDACION:
        messages.error(request, "El caso ya no admite una decisión de validación.")
        return redirect("nota_detail", pk=note.pk)
    latest = note.validaciones.filter(eliminado_en__isnull=True).first()
    if not latest:
        messages.error(request, "Ejecuta una validación antes de tomar la decisión.")
        return redirect("validation_detail", pk=note.pk)
    form = DecisionValidacionForm(request.POST)
    if not form.is_valid():
        return render(
            request,
            "credit_notes/validation_detail.html",
            {"nota": note, "validacion": latest, "form": form},
        )
    decision = form.cleaned_data["decision"]
    observations = form.cleaned_data["observaciones"]
    with transaction.atomic():
        note.contador = request.user
        note.observaciones_validacion = observations
        if decision == DecisionValidacionForm.Decision.APROBAR:
            note.estado_flujo = NotaCredito.EstadoFlujo.VALIDADA
            note.validado_en = timezone.now()
            action = "VALIDACION_APROBADA"
            description = "El contador aprobó el caso para negociación."
        elif decision == DecisionValidacionForm.Decision.CORREGIR:
            note.estado_flujo = NotaCredito.EstadoFlujo.CORRECCION_REQUERIDA
            action = "CORRECCION_SOLICITADA"
            description = "El contador devolvió el caso a recepción para corrección."
        else:
            note.estado_flujo = NotaCredito.EstadoFlujo.RECHAZADA
            action = "CASO_RECHAZADO"
            description = "El contador rechazó el caso."
        note.save()
        registrar_evento(
            note,
            request.user,
            action,
            description,
            {"observaciones": observations, "resultado_reglas": latest.resultado},
        )
    messages.success(request, "Decisión registrada con trazabilidad.")
    return redirect("nota_detail", pk=note.pk)


@role_required(3)
def negotiation_queue(request):
    notes = NotaCredito.objects.filter(eliminado_en__isnull=True).filter(
        estado_flujo__in=[
            NotaCredito.EstadoFlujo.VALIDADA,
            NotaCredito.EstadoFlujo.EN_NEGOCIACION,
            NotaCredito.EstadoFlujo.PENDIENTE_CONFIRMACIONES,
            NotaCredito.EstadoFlujo.LISTA_LIQUIDACION,
        ]
    ).select_related("cliente_vendedor", "contador", "vendedor")
    return render(request, "credit_notes/negotiation_queue.html", {"notas": notes})


@role_required(3)
def negotiation_edit(request, pk):
    note = _get_note_for_user(request.user, pk)
    if note.estado_flujo not in {
        NotaCredito.EstadoFlujo.VALIDADA,
        NotaCredito.EstadoFlujo.EN_NEGOCIACION,
    }:
        messages.error(request, "El caso no está disponible para preparar negociación.")
        return redirect("nota_detail", pk=note.pk)
    order = getattr(note, "orden_negociacion", None)
    previous_contract = None
    if order:
        previous_contract = (str(order.comprador_id), str(order.valor_venta), order.fecha_propuesta, order.vigencia_hasta, order.terminos, order.observaciones)
    if request.method == "POST":
        form = OrdenNegociacionForm(request.POST, instance=order, nota=note)
        if form.is_valid():
            with transaction.atomic():
                order = form.save(commit=False)
                order.nota = note
                order.preparado_por = request.user
                order.eliminado_en = None
                order.eliminado_por = None
                order.motivo_eliminacion = ""
                order.save()
                current_contract = (str(order.comprador_id), str(order.valor_venta), order.fecha_propuesta, order.vigencia_hasta, order.terminos, order.observaciones)
                if previous_contract is not None and previous_contract != current_contract and order.solicitudes.exists():
                    old_version = order.version
                    order.solicitudes.filter(version_contrato=old_version, estado=SolicitudAprobacion.Estado.PENDIENTE).update(estado=SolicitudAprobacion.Estado.EXPIRADA)
                    order.version += 1
                    order.estado = OrdenNegociacion.Estado.BORRADOR
                    order.save(update_fields=["version", "estado", "actualizado_en"])
                    registrar_evento(note, request.user, "CONTRATO_REAJUSTADO", f"Se creó la versión {order.version}; los enlaces anteriores quedaron invalidados.", {"version_anterior": old_version, "version_nueva": order.version})
                note.cliente_comprador = order.comprador
                note.vendedor = request.user
                note.estado_flujo = NotaCredito.EstadoFlujo.EN_NEGOCIACION
                if not note.iniciado_negociacion_en:
                    note.iniciado_negociacion_en = timezone.now()
                note.save()
                registrar_evento(
                    note,
                    request.user,
                    "ORDEN_PREPARADA",
                    "El vendedor creó o actualizó el borrador de negociación.",
                    {"valor_venta": str(order.valor_venta), "comprador": str(order.comprador_id)},
                )
            messages.success(request, "Borrador de negociación guardado.")
            return redirect("nota_detail", pk=note.pk)
    else:
        form = OrdenNegociacionForm(instance=order, nota=note)
    return render(
        request,
        "credit_notes/negotiation_form.html",
        {"form": form, "nota": note, "orden": order},
    )


@role_required(3)
def negotiation_delete(request, pk):
    note = _get_note_for_user(request.user, pk)
    order = get_object_or_404(OrdenNegociacion, nota=note, eliminado_en__isnull=True)
    response = _delete_view(request, order, "Eliminar negociación", "nota_detail", note)
    if request.method == "POST" and isinstance(response, HttpResponse) and response.status_code == 302:
        note.estado_flujo = NotaCredito.EstadoFlujo.VALIDADA
        note.cliente_comprador = None
        note.save(update_fields=["estado_flujo", "cliente_comprador", "actualizado_en"])
    return response


@role_required(3)
@require_POST
def report_generate(request, pk):
    note = _get_note_for_user(request.user, pk)
    order = getattr(note, "orden_negociacion", None)
    if order and order.eliminado_en:
        order = None
    version = order.actualizado_en.isoformat() if order else note.actualizado_en.isoformat()
    key = f"reporte:{note.pk}:{version}"
    try:
        OperacionIdempotente.objects.create(clave=key, tipo="REPORTE_IA")
    except IntegrityError:
        messages.info(request, "El reporte para esta versión ya fue generado o está en proceso.")
        return redirect("nota_detail", pk=note.pk)
    try:
        report = generar_reporte_negociacion(note, request.user)
        OperacionIdempotente.objects.filter(clave=key).update(completada_en=timezone.now(), resultado_id=str(report.pk))
        messages.success(request, "Gemini generó el borrador para revisión.")
        return redirect("report_detail", report_id=report.pk)
    except (ValueError, GeminiServiceError) as exc:
        OperacionIdempotente.objects.filter(clave=key, completada_en__isnull=True).delete()
        messages.error(request, str(exc))
        return redirect("nota_detail", pk=note.pk)


@role_required(3)
def report_detail(request, report_id):
    report = get_object_or_404(
        ReporteIA.objects.select_related("nota", "generado_por"), pk=report_id
    )
    return render(request, "credit_notes/report_detail.html", {"reporte": report})


@role_required(3)
def report_pdf(request, report_id):
    report = get_object_or_404(ReporteIA, pk=report_id)
    pdf_bytes = build_negotiation_pdf(report)
    filename = f"negociacion-{report.nota.numero_titulo}.pdf".replace(" ", "-")
    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


@role_required(3)
@require_POST
def approval_requests_create(request, pk):
    note = _get_note_for_user(request.user, pk)
    order = getattr(note, "orden_negociacion", None)
    if not order or order.eliminado_en:
        messages.error(request, "Primero crea la orden de negociación.")
        return redirect("nota_detail", pk=note.pk)
    if not note.reportes_ia.exists():
        messages.error(request, "Genera y revisa al menos un reporte antes de solicitar confirmaciones.")
        return redirect("nota_detail", pk=note.pk)
    with transaction.atomic():
        snapshot = {"version": order.version, "numero_titulo": note.numero_titulo, "vendedor": note.cliente_vendedor.nombre_razon_social, "comprador": order.comprador.nombre_razon_social, "valor_venta": str(order.valor_venta), "porcentaje_descuento": str(order.porcentaje_descuento), "fecha_propuesta": order.fecha_propuesta.isoformat(), "vigencia_hasta": order.vigencia_hasta.isoformat() if order.vigencia_hasta else "", "terminos": order.terminos, "observaciones": order.observaciones}
        seller_request, _ = SolicitudAprobacion.objects.get_or_create(
            orden=order,
            parte=SolicitudAprobacion.Parte.VENDEDOR,
            version_contrato=order.version,
            defaults={"cliente": note.cliente_vendedor, "contrato_snapshot": snapshot},
        )
        buyer_request, _ = SolicitudAprobacion.objects.get_or_create(
            orden=order,
            parte=SolicitudAprobacion.Parte.COMPRADOR,
            version_contrato=order.version,
            defaults={"cliente": order.comprador, "contrato_snapshot": snapshot},
        )
        order.estado = OrdenNegociacion.Estado.ENVIADA_CONFIRMACION
        order.save(update_fields=["estado", "actualizado_en"])
        note.estado_flujo = NotaCredito.EstadoFlujo.PENDIENTE_CONFIRMACIONES
        note.save(update_fields=["estado_flujo", "actualizado_en"])
        registrar_evento(
            note,
            request.user,
            "CONFIRMACIONES_SOLICITADAS",
            "Se generaron enlaces únicos para vendedor y comprador.",
            {"solicitudes_generadas": 2, "version_contrato": order.version},
        )
    messages.success(request, "Enlaces de confirmación generados.")
    return redirect("approval_links", pk=note.pk)


@role_required(3)
def approval_links(request, pk):
    note = _get_note_for_user(request.user, pk)
    order = getattr(note, "orden_negociacion", None)
    if not order or order.eliminado_en:
        messages.error(request, "No existe orden de negociación.")
        return redirect("nota_detail", pk=note.pk)
    base_url = settings.PUBLIC_BASE_URL or request.build_absolute_uri("/").rstrip("/")
    requests_data = []
    for approval in order.solicitudes.select_related("cliente").order_by("-version_contrato", "parte"):
        url = f"{base_url}{reverse('public_approval', kwargs={'token': approval.token})}"
        requests_data.append((approval, url))
    return render(
        request,
        "credit_notes/approval_links.html",
        {"nota": note, "orden": order, "solicitudes": requests_data},
    )


def public_approval(request, token):
    approval = get_object_or_404(
        SolicitudAprobacion.objects.select_related(
            "orden__nota__cliente_vendedor", "orden__comprador", "cliente"
        ),
        token=token, orden__eliminado_en__isnull=True, orden__nota__eliminado_en__isnull=True,
    )
    if approval.estado != SolicitudAprobacion.Estado.PENDIENTE:
        return render(
            request,
            "credit_notes/public_approval_done.html",
            {"solicitud": approval},
        )
    if request.method == "POST":
        form = ConfirmacionPublicaForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                approval = SolicitudAprobacion.objects.select_for_update().get(pk=approval.pk)
                if approval.estado != SolicitudAprobacion.Estado.PENDIENTE:
                    return redirect("public_approval", token=approval.token)
                approval.estado = form.cleaned_data["decision"]
                approval.confirmado_por = form.cleaned_data["nombre"]
                approval.correo_confirmacion = form.cleaned_data["correo"]
                approval.comentario = form.cleaned_data["comentario"]
                approval.confirmado_en = timezone.now()
                approval.save()
                note = approval.orden.nota
                registrar_evento(
                    note,
                    None,
                    "CONFIRMACION_EXTERNA",
                    f"La parte {approval.get_parte_display()} registró su decisión: {approval.get_estado_display()}.",
                    {"solicitud": str(approval.id)},
                )
                all_requests = list(approval.orden.solicitudes.filter(version_contrato=approval.version_contrato))
                if all_requests and all(
                    item.estado == SolicitudAprobacion.Estado.APROBADA
                    for item in all_requests
                ):
                    approval.orden.estado = OrdenNegociacion.Estado.CONFIRMADA_PARTES
                    approval.orden.save(update_fields=["estado", "actualizado_en"])
                    note.estado_flujo = NotaCredito.EstadoFlujo.LISTA_LIQUIDACION
                    note.save(update_fields=["estado_flujo", "actualizado_en"])
                    registrar_evento(
                        note,
                        None,
                        "PARTES_CONFIRMADAS",
                        "Ambas partes confirmaron. El caso queda listo para solicitar aprobación regulada.",
                    )
                elif approval.estado == SolicitudAprobacion.Estado.RECHAZADA:
                    approval.orden.solicitudes.filter(version_contrato=approval.version_contrato, estado=SolicitudAprobacion.Estado.PENDIENTE).exclude(pk=approval.pk).update(estado=SolicitudAprobacion.Estado.EXPIRADA)
                    note.estado_flujo = NotaCredito.EstadoFlujo.EN_NEGOCIACION
                    note.save(update_fields=["estado_flujo", "actualizado_en"])
                    registrar_evento(note, None, "NEGOCIACION_FALLIDA", f"La versión {approval.version_contrato} fue rechazada por {approval.get_parte_display()} y queda disponible para reajuste.", {"version": approval.version_contrato, "parte": approval.parte, "comentario": approval.comentario})
            return redirect("public_approval", token=approval.token)
    else:
        form = ConfirmacionPublicaForm()
    return render(
        request,
        "credit_notes/public_approval.html",
        {"solicitud": approval, "form": form},
    )


@role_required(3)
@require_POST
def close_demo(request, pk):
    note = _get_note_for_user(request.user, pk)
    if note.estado_flujo != NotaCredito.EstadoFlujo.LISTA_LIQUIDACION:
        messages.error(request, "El caso aún no tiene las confirmaciones requeridas.")
        return redirect("nota_detail", pk=note.pk)
    note.estado_flujo = NotaCredito.EstadoFlujo.CERRADA_DEMO
    note.save(update_fields=["estado_flujo", "actualizado_en"])
    registrar_evento(
        note,
        request.user,
        "CIERRE_DEMO",
        "Se registró un cierre demostrativo. No se ejecutó transferencia, liquidación ni endoso.",
    )
    messages.success(request, "Cierre demostrativo registrado sin ejecutar acciones reguladas.")
    return redirect("nota_detail", pk=note.pk)


@role_required(1)
@require_GET
def api_client_lookup(request):
    ruc = request.GET.get("ruc", "").strip()
    client_id = request.GET.get("cliente_id", "").strip()
    if client_id:
        client = Cliente.objects.filter(pk=client_id).first()
    else:
        if len(ruc) < 4:
            return JsonResponse({"found": False, "message": "Ingrese al menos 4 dígitos."})
        client = Cliente.objects.filter(ruc_identificacion=ruc).first()
    if not client:
        return JsonResponse({"found": False})
    previous = list(
        NotaCredito.objects.filter(cliente_vendedor=client)
        .values(
            "numero_titulo",
            "tipo_nota",
            "origen_tributario",
            "valor_nominal",
            "saldo_disponible",
            "minimo_recibir",
            "estado_flujo",
            "actualizado_en",
        )[:5]
    )
    for item in previous:
        for key in ("valor_nominal", "saldo_disponible", "minimo_recibir"):
            item[key] = str(item[key])
        item["actualizado_en"] = item["actualizado_en"].isoformat()
    return JsonResponse(
        {
            "found": True,
            "cliente": {
                "id": str(client.id),
                "nombre": client.nombre_razon_social,
                "ruc": client.ruc_identificacion,
                "tipo": client.tipo_relacion,
                "autorizado": client.autorizacion_consulta,
            },
            "antecedentes": previous,
        }
    )
