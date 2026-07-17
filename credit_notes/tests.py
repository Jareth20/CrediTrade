from datetime import date
from decimal import Decimal
from unittest.mock import patch
from types import SimpleNamespace

from django.test import Client as HttpClient, TestCase, override_settings
from django.urls import reverse

from accounts.models import Operador
from credit_notes.ai_services import (
    GeminiServiceError,
    _call_gemini,
    generar_reporte_negociacion,
    generar_sugerencias_nota,
)
from credit_notes.gemini_service import (
    GeminiInvalidResponseError,
    GeminiQuotaExceededError,
    GeminiRateLimitError,
    GeminiTimeoutError,
    GeminiUnavailableError,
    _get_gemini_client,
    call_structured,
)
from credit_notes.models import (
    Cliente,
    DocumentoRespaldo,
    NotaCredito,
    OrdenNegociacion,
    RegistroSimuladoTitulo,
    ReporteIA,
    SugerenciaIA,
    SolicitudAprobacion,
    EjecucionAgente,
    EventoAgente,
    MemoriaAgente,
    FragmentoDocumento,
    OperacionIdempotente,
)
from credit_notes.agents import iniciar_analisis, registrar_decision
from credit_notes.rag import (
    fragmentar_texto,
    indexar_documento,
    indexar_documentos,
    preparar_evidencia,
)
from pydantic import BaseModel
from credit_notes.services import enviar_a_validacion, ejecutar_validacion_simulada


@override_settings(
    SECURE_SSL_REDIRECT=False,
    GEMINI_API_KEY="test-key",
    GEMINI_MODEL="gemini-test",
    GEMINI_FAST_MODEL="gemini-test",
    GEMINI_DEEP_MODEL="gemini-test",
    GEMINI_MAX_RETRIES=1,
    GEMINI_RETRY_BASE_SECONDS=0.01,
    GEMINI_MAX_RETRY_WAIT_SECONDS=8,
    GEMINI_QUOTA_COOLDOWN_SECONDS=60,
    GEMINI_CACHE_SECONDS=60,
)
class WorkflowTests(TestCase):
    def setUp(self):
        _get_gemini_client.cache_clear()
        self.reception = Operador.objects.create_user(
            username="op1",
            password="test-pass-123",
            puede_recepcionar=True,
        )
        self.accountant = Operador.objects.create_user(
            username="op2",
            password="test-pass-123",
            puede_validar=True,
        )
        self.seller_operator = Operador.objects.create_user(
            username="op3",
            password="test-pass-123",
            puede_negociar=True,
        )
        self.full_operator = Operador.objects.create_user(
            username="op-total",
            password="test-pass-123",
            puede_recepcionar=True,
            puede_validar=True,
            puede_negociar=True,
        )
        self.seller = Cliente.objects.create(
            tipo_relacion=Cliente.TipoRelacion.VENDEDOR,
            ruc_identificacion="0999999999001",
            nombre_razon_social="Vendedor Demo",
            estado_cuenta_sri=Cliente.EstadoCuentaSRI.ACTIVO,
            autorizacion_consulta=True,
            creado_por=self.reception,
        )
        self.buyer = Cliente.objects.create(
            tipo_relacion=Cliente.TipoRelacion.COMPRADOR,
            ruc_identificacion="0999999998001",
            nombre_razon_social="Comprador Demo",
            estado_cuenta_sri=Cliente.EstadoCuentaSRI.ACTIVO,
            autorizacion_consulta=True,
            creado_por=self.seller_operator,
        )
        self.note = NotaCredito.objects.create(
            numero_titulo="SIM-TEST-001",
            cliente_vendedor=self.seller,
            tipo_nota=NotaCredito.TipoNota.ISD,
            origen_tributario=NotaCredito.OrigenTributario.DEVOLUCION_ISD,
            valor_nominal=Decimal("1000.00"),
            saldo_disponible=Decimal("950.00"),
            minimo_recibir=Decimal("900.00"),
            fecha_emision=date.today(),
            estado_flujo=NotaCredito.EstadoFlujo.BORRADOR,
            recepcionista=self.reception,
        )
        RegistroSimuladoTitulo.objects.create(
            numero_titulo=self.note.numero_titulo,
            titular_ruc=self.seller.ruc_identificacion,
            tipo_nota=self.note.tipo_nota,
            valor_nominal=self.note.valor_nominal,
            saldo=self.note.saldo_disponible,
            estado="VIGENTE",
        )

    def add_document(self):
        return DocumentoRespaldo.objects.create(
            nota=self.note,
            tipo_documento=DocumentoRespaldo.TipoDocumento.NOTA_CREDITO,
            nombre="Respaldo",
            texto_extraido="Documento de prueba",
            cargado_por=self.reception,
        )

    def prepare_order(self):
        self.add_document()
        enviar_a_validacion(self.note, self.reception)
        ejecutar_validacion_simulada(self.note, self.accountant)
        self.note.contador = self.accountant
        self.note.estado_flujo = NotaCredito.EstadoFlujo.VALIDADA
        self.note.save()
        order = OrdenNegociacion.objects.create(
            nota=self.note,
            comprador=self.buyer,
            valor_venta=Decimal("925.00"),
            terminos="Pago sujeto a aprobación externa.",
            preparado_por=self.seller_operator,
        )
        self.note.cliente_comprador = self.buyer
        self.note.vendedor = self.seller_operator
        self.note.estado_flujo = NotaCredito.EstadoFlujo.EN_NEGOCIACION
        self.note.save()
        return order

    def test_cannot_submit_without_document(self):
        with self.assertRaises(ValueError):
            enviar_a_validacion(self.note, self.reception)

    def test_operator_can_have_all_three_roles(self):
        self.assertTrue(self.full_operator.tiene_rol(1))
        self.assertTrue(self.full_operator.tiene_rol(2))
        self.assertTrue(self.full_operator.tiene_rol(3))

        client = HttpClient()
        client.force_login(self.full_operator)
        self.assertEqual(client.get(reverse("antecedentes")).status_code, 200)
        self.assertEqual(client.get(reverse("validation_queue")).status_code, 200)
        self.assertEqual(client.get(reverse("negotiation_queue")).status_code, 200)

    @patch("credit_notes.ai_services._call_gemini")
    def test_end_to_end_report_uses_gemini_only(self, mock_call):
        order = self.prepare_order()

        def fake_call(prompt, schema_model, **_kwargs):
            return schema_model(
                titulo=f"Ficha de negociación - {self.note.numero_titulo}",
                resumen_ejecutivo="Resumen generado por Gemini.",
                puntos_clave=["Saldo confirmado en la fuente simulada."],
                riesgos_y_pendientes=["Requiere aprobación humana."],
                siguiente_accion="Solicitar confirmaciones.",
                texto_carta="Borrador de carta generado por Gemini.",
            )

        mock_call.side_effect = fake_call
        report = generar_reporte_negociacion(self.note, self.seller_operator)
        self.assertIn(self.note.numero_titulo, report.titulo)
        self.assertEqual(report.modelo_ia, "gemini-test")

        seller_request = SolicitudAprobacion.objects.create(
            orden=order,
            parte=SolicitudAprobacion.Parte.VENDEDOR,
            cliente=self.seller,
        )
        buyer_request = SolicitudAprobacion.objects.create(
            orden=order,
            parte=SolicitudAprobacion.Parte.COMPRADOR,
            cliente=self.buyer,
        )
        self.assertNotEqual(seller_request.token, buyer_request.token)

    @override_settings(GEMINI_API_KEY="")
    def test_report_has_no_local_fallback(self):
        self.prepare_order()
        with self.assertRaises(GeminiServiceError):
            generar_reporte_negociacion(self.note, self.seller_operator)
        self.assertFalse(ReporteIA.objects.exists())

    def test_confirmations_do_not_require_an_ai_report_or_pdf(self):
        order = self.prepare_order()
        client = HttpClient()
        client.force_login(self.seller_operator)

        response = client.post(
            reverse("approval_requests_create", args=[self.note.pk])
        )

        self.assertRedirects(
            response, reverse("approval_links", args=[self.note.pk])
        )
        self.assertFalse(ReporteIA.objects.exists())
        self.assertEqual(order.solicitudes.count(), 2)
        self.note.refresh_from_db()
        self.assertEqual(
            self.note.estado_flujo,
            NotaCredito.EstadoFlujo.PENDIENTE_CONFIRMACIONES,
        )

    @patch("credit_notes.ai_services._call_gemini")
    def test_suggestions_are_saved_only_after_valid_gemini_response(self, mock_call):
        self.add_document()

        def fake_call(prompt, schema_model, **_kwargs):
            return schema_model(
                sugerencias=[
                    {
                        "campo": "estado_fuente",
                        "valor_sugerido": "VIGENTE",
                        "confianza": 0.92,
                        "fuente": "Documento de prueba",
                        "evidencia": "El texto del respaldo indica estado vigente.",
                    }
                ]
            )

        mock_call.side_effect = fake_call
        suggestions = generar_sugerencias_nota(self.note, self.reception)
        self.assertEqual(len(suggestions), 1)
        self.assertEqual(suggestions[0].generada_por_modelo, "gemini-test")

    def test_role_access(self):
        client = HttpClient()
        client.force_login(self.reception)
        response = client.get(reverse("validation_queue"))
        self.assertEqual(response.status_code, 302)

        client.force_login(self.accountant)
        response = client.get(reverse("validation_queue"))
        self.assertEqual(response.status_code, 200)


class AgenticArchitectureTests(WorkflowTests):
    def _rag_result(self):
        return {
            "conclusion": "Evidencia interna recuperada.",
            "evidencia": [{
                "fragmento_id": "f-1", "documento": "Respaldo", "nota": self.note.numero_titulo,
                "cliente": self.seller.nombre_razon_social, "tipo_documento": "NOTA_CREDITO",
                "fuente": "Operador", "seccion": "Fragmento 1", "fecha": "2026-01-01T00:00:00Z",
                "texto": "Saldo disponible respaldado por documento interno.", "relevancia": 0.91,
            }],
            "fuentes": [{"documento": "Respaldo", "nota": self.note.numero_titulo, "fuente": "Operador", "fecha": "2026-01-01", "seccion": "Fragmento 1"}],
            "confianza": 0.91,
            "advertencias": ["Requiere revision humana."],
            "siguiente_accion": "Contrastar fuente.",
        }

    @patch("credit_notes.agents.preparar_evidencia")
    def test_graph_selects_agents_and_persists_checkpoint(self, mocked_rag):
        mocked_rag.return_value = self._rag_result()
        self.add_document()
        execution, created = iniciar_analisis(self.note, self.reception)
        self.assertTrue(created)
        self.assertEqual(execution.estado, EjecucionAgente.Estado.ESPERANDO_HUMANO)
        self.assertEqual(execution.nodo_pendiente, "revision_operador")
        nodes = execution.estado_compartido["nodos_ejecutados"]
        self.assertEqual(nodes, ["supervisor", "ingreso_documental", "antecedentes_rag", "validacion_riesgos", "explicacion", "checkpoint_humano"])
        self.assertTrue(EventoAgente.objects.filter(ejecucion=execution, agente="antecedentes_rag").exists())

    @patch("credit_notes.agents.preparar_evidencia")
    def test_double_submission_returns_same_execution(self, mocked_rag):
        mocked_rag.return_value = self._rag_result()
        first, created = iniciar_analisis(self.note, self.reception)
        second, created_again = iniciar_analisis(self.note, self.reception)
        self.assertTrue(created)
        self.assertFalse(created_again)
        self.assertEqual(first.pk, second.pk)

    @patch("credit_notes.agents.preparar_evidencia")
    def test_human_decision_creates_separate_long_term_memory(self, mocked_rag):
        mocked_rag.return_value = self._rag_result()
        execution, _ = iniciar_analisis(self.note, self.reception)
        registrar_decision(execution, self.reception, "ACEPTAR", "Evidencia revisada.")
        execution.refresh_from_db()
        self.assertEqual(execution.estado, EjecucionAgente.Estado.COMPLETADA)
        memory = MemoriaAgente.objects.get(operador=self.reception)
        self.assertEqual(memory.contenido["decision"], "ACEPTAR")
        self.assertFalse(MemoriaAgente.objects.filter(operador=self.accountant).exists())

    @patch("credit_notes.agents.preparar_evidencia")
    def test_other_operator_cannot_decide_private_checkpoint(self, mocked_rag):
        mocked_rag.return_value = self._rag_result()
        execution, _ = iniciar_analisis(self.note, self.reception)
        with self.assertRaises(PermissionError):
            registrar_decision(execution, self.accountant, "ACEPTAR")

    def test_agent_actions_require_post(self):
        client = HttpClient()
        client.force_login(self.reception)
        self.assertEqual(client.get(reverse("agent_analysis_start", args=[self.note.pk])).status_code, 405)

    @patch("credit_notes.views.generar_explicacion_validacion")
    def test_validation_explanation_can_retry_without_repeating_rules(self, mocked_explanation):
        self.add_document()
        enviar_a_validacion(self.note, self.reception)
        ejecutar_validacion_simulada(self.note, self.accountant)
        mocked_explanation.return_value = "Explicación revisable."
        client = HttpClient()
        client.force_login(self.accountant)
        response = client.post(reverse("validation_explanation_retry", args=[self.note.pk]))
        self.assertEqual(response.status_code, 302)
        mocked_explanation.assert_called_once()
        self.assertEqual(self.note.validaciones.count(), 1)
        self.assertTrue(self.note.eventos.filter(accion="EXPLICACION_VALIDACION_GENERADA").exists())

    def test_rule_validation_evidence_cannot_be_edited_or_deleted(self):
        self.add_document()
        enviar_a_validacion(self.note, self.reception)
        validation = ejecutar_validacion_simulada(self.note, self.accountant)
        client = HttpClient()
        client.force_login(self.accountant)
        self.assertEqual(client.get(f"/validaciones/{validation.pk}/editar/").status_code, 404)
        self.assertEqual(client.post(f"/validaciones/{validation.pk}/editar/", {}).status_code, 404)
        self.assertEqual(client.get(f"/validaciones/{validation.pk}/eliminar/").status_code, 404)

    @patch("credit_notes.agents.preparar_evidencia")
    def test_agent_center_view_and_post(self, mocked_rag):
        mocked_rag.return_value = self._rag_result()
        client = HttpClient()
        client.force_login(self.reception)
        response = client.post(reverse("agent_analysis_start", args=[self.note.pk]))
        self.assertEqual(response.status_code, 302)
        detail = client.get(reverse("nota_detail", args=[self.note.pk]))
        self.assertContains(detail, "Centro de analisis asistido")
        self.assertContains(detail, "RAG: evidencia recuperada")

    def test_note_detail_organizes_information_in_accessible_sections(self):
        client = HttpClient()
        client.force_login(self.reception)
        detail = client.get(reverse("nota_detail", args=[self.note.pk]))

        self.assertEqual(detail.status_code, 200)
        for section in (
            "resumen",
            "documentos",
            "analisis",
            "validacion",
            "negociacion",
            "trazabilidad",
        ):
            self.assertContains(detail, f'id="{section}"')
            self.assertContains(detail, f'data-section="{section}"')
        self.assertContains(detail, 'aria-label="Secciones del expediente"')
        self.assertContains(detail, 'aria-current="page"')

    def test_chunking_is_bounded_and_overlapping(self):
        chunks = fragmentar_texto(" ".join(["evidencia"] * 400), tamano=180, solapamiento=30)
        self.assertGreater(len(chunks), 2)
        self.assertTrue(all(len(chunk) <= 180 for chunk in chunks))

    @patch("credit_notes.rag.generar_embeddings")
    def test_rag_indexes_vectors_with_source_metadata(self, mocked_embeddings):
        document = self.add_document()
        mocked_embeddings.return_value = [[0.1] * 768]
        created = indexar_documento(document)
        self.assertEqual(len(created), 1)
        chunk = FragmentoDocumento.objects.get(documento=document)
        self.assertEqual(chunk.nota, self.note)
        self.assertEqual(chunk.cliente, self.seller)
        self.assertEqual(chunk.fuente, document.fuente)

    @patch("credit_notes.rag.generar_embeddings")
    def test_rag_batches_documents_and_deduplicates_context(self, mocked_embeddings):
        first = self.add_document()
        second = DocumentoRespaldo.objects.create(
            nota=self.note,
            tipo_documento=DocumentoRespaldo.TipoDocumento.OTRO,
            nombre="Segundo respaldo",
            texto_extraido=first.texto_extraido,
            cargado_por=self.reception,
        )

        def vectors(texts, **_kwargs):
            return [[0.1] * 768 for _ in texts]

        mocked_embeddings.side_effect = vectors
        indexed = indexar_documentos([first, second])
        result = preparar_evidencia(self.note)

        self.assertEqual(len(indexed), 2)
        self.assertEqual(mocked_embeddings.call_count, 2)
        document_batch = mocked_embeddings.call_args_list[0].args[0]
        self.assertEqual(len(document_batch), 2)
        self.assertEqual(len(result["evidencia"]), 1)
        self.assertLessEqual(
            sum(len(item["texto"]) for item in result["evidencia"]),
            4000,
        )

    @patch("credit_notes.rag.buscar_fragmentos", return_value=[])
    @patch("credit_notes.rag.indexar_documento", return_value=[])
    def test_rag_states_when_evidence_is_insufficient(self, _index, _search):
        result = preparar_evidencia(self.note)
        self.assertEqual(result["confianza"], 0.0)
        self.assertIn("No existe evidencia", result["conclusion"])

    @patch("credit_notes.gemini_service._get_gemini_client")
    def test_gemini_timeout_is_controlled(self, mocked_client):
        class Schema(BaseModel):
            value: str
        mocked_client.return_value.interactions.create.side_effect = TimeoutError(
            "provider timeout"
        )
        with self.assertRaises(GeminiTimeoutError):
            _call_gemini("prompt", Schema)

    @patch("google.genai.Client")
    def test_sdk_retries_are_disabled_to_avoid_nested_backoff(self, mocked_client):
        _get_gemini_client.cache_clear()
        _get_gemini_client("isolated-test-key", 1000)
        options = mocked_client.call_args.kwargs["http_options"]
        self.assertEqual(options.retry_options.attempts, 1)

    @patch("credit_notes.gemini_service.time.sleep")
    @patch("credit_notes.gemini_service._get_gemini_client")
    def test_gemini_rate_limit_retries_once(self, mocked_client, mocked_sleep):
        class Schema(BaseModel):
            value: str
        mocked_client.return_value.interactions.create.side_effect = [
            RuntimeError("429 too_many_requests Please retry in 4.5s."),
            SimpleNamespace(output_text='{"value":"ok"}'),
        ]
        result = _call_gemini("prompt", Schema)
        self.assertEqual(result.value, "ok")
        mocked_sleep.assert_called_once_with(4.5)
        self.assertEqual(mocked_client.return_value.interactions.create.call_count, 2)

    @patch("credit_notes.gemini_service.time.sleep")
    @patch("credit_notes.gemini_service._get_gemini_client")
    def test_gemini_does_not_block_for_long_rate_limit(self, mocked_client, mocked_sleep):
        class Schema(BaseModel):
            value: str
        mocked_client.return_value.interactions.create.side_effect = RuntimeError(
            "429 too_many_requests free_tier_requests, limit: 20; "
            "check your plan and billing details. Please retry in 44.1s."
        )
        with self.assertRaises(GeminiRateLimitError):
            _call_gemini("prompt", Schema)
        mocked_sleep.assert_not_called()
        self.assertEqual(mocked_client.return_value.interactions.create.call_count, 1)

    @patch("credit_notes.gemini_service.time.sleep")
    @patch("credit_notes.gemini_service._get_gemini_client")
    def test_gemini_503_retries_once_then_succeeds(self, mocked_client, mocked_sleep):
        class Schema(BaseModel):
            value: str

        mocked_client.return_value.interactions.create.side_effect = [
            RuntimeError("Error code: 503 UNAVAILABLE"),
            SimpleNamespace(output_text='{"value":"ok"}'),
        ]
        result = _call_gemini("503 prompt", Schema, operation="503-test")
        self.assertEqual(result.value, "ok")
        self.assertEqual(mocked_client.return_value.interactions.create.call_count, 2)
        mocked_sleep.assert_called_once()

    @patch("credit_notes.gemini_service.time.sleep")
    @patch("credit_notes.gemini_service._get_gemini_client")
    def test_transient_errors_stop_at_configured_attempts(self, mocked_client, mocked_sleep):
        class Schema(BaseModel):
            value: str

        mocked_client.return_value.interactions.create.side_effect = RuntimeError(
            "Error code: 503 UNAVAILABLE"
        )
        with self.assertRaises(GeminiUnavailableError):
            _call_gemini("max attempts", Schema, operation="attempt-test")
        self.assertEqual(mocked_client.return_value.interactions.create.call_count, 2)
        self.assertEqual(mocked_sleep.call_count, 1)

    @patch("credit_notes.gemini_service.time.sleep")
    @patch("credit_notes.gemini_service._get_gemini_client")
    def test_hard_quota_has_no_retry_and_activates_cooldown(self, mocked_client, mocked_sleep):
        class Schema(BaseModel):
            value: str

        mocked_client.return_value.interactions.create.side_effect = RuntimeError(
            "429 RESOURCE_EXHAUSTED limit: 0; billing not enabled"
        )
        with self.assertRaises(GeminiQuotaExceededError):
            _call_gemini("quota", Schema, operation="quota-test")
        with self.assertRaises(GeminiQuotaExceededError):
            _call_gemini("quota changed", Schema, operation="quota-test")
        self.assertEqual(mocked_client.return_value.interactions.create.call_count, 1)
        mocked_sleep.assert_not_called()
        self.assertTrue(
            OperacionIdempotente.objects.filter(
                tipo="GEMINI_COOLDOWN", error_tipo="CUOTA_AGOTADA"
            ).exists()
        )

    @patch("credit_notes.gemini_service._get_gemini_client")
    def test_structured_response_cache_hit_avoids_second_call(self, mocked_client):
        class Schema(BaseModel):
            value: str

        mocked_client.return_value.interactions.create.return_value = SimpleNamespace(
            output_text='{"value":"cached"}'
        )
        first = call_structured("same", Schema, operation="cache-test")
        second = call_structured("same", Schema, operation="cache-test")
        self.assertEqual(first.value, second.value)
        self.assertEqual(mocked_client.return_value.interactions.create.call_count, 1)
        request_kwargs = mocked_client.return_value.interactions.create.call_args.kwargs
        self.assertEqual(request_kwargs["model"], "gemini-test")
        self.assertEqual(
            request_kwargs["generation_config"]["thinking_level"], "minimal"
        )
        self.assertLessEqual(
            request_kwargs["generation_config"]["max_output_tokens"], 512
        )
        self.assertFalse(request_kwargs["store"])
        self.assertTrue(
            OperacionIdempotente.objects.filter(
                tipo__startswith="GEMINI_CACHE_"
            ).exists()
        )

    @patch("credit_notes.gemini_service._get_gemini_client")
    def test_cache_is_invalidated_when_prompt_changes(self, mocked_client):
        class Schema(BaseModel):
            value: str

        mocked_client.return_value.interactions.create.side_effect = [
            SimpleNamespace(output_text='{"value":"one"}'),
            SimpleNamespace(output_text='{"value":"two"}'),
        ]
        first = call_structured("version one", Schema, operation="invalidate-test")
        second = call_structured("version two", Schema, operation="invalidate-test")
        self.assertEqual((first.value, second.value), ("one", "two"))
        self.assertEqual(mocked_client.return_value.interactions.create.call_count, 2)

    @patch("credit_notes.gemini_service._get_gemini_client")
    def test_invalid_structured_response_is_controlled(self, mocked_client):
        class Schema(BaseModel):
            value: str

        mocked_client.return_value.interactions.create.return_value = SimpleNamespace(
            output_text='{"unexpected":true}'
        )
        with self.assertRaises(GeminiInvalidResponseError):
            call_structured("invalid", Schema, operation="invalid-test")

    @patch("credit_notes.views.generar_sugerencias_nota", return_value=[])
    def test_suggestion_double_submission_calls_service_once(self, mocked_generate):
        client = HttpClient()
        client.force_login(self.reception)
        url = reverse("ai_generate_suggestions", args=[self.note.pk])
        self.assertEqual(client.post(url).status_code, 302)
        self.assertEqual(client.post(url).status_code, 302)
        mocked_generate.assert_called_once()

    @patch("credit_notes.views.generar_sugerencias_nota")
    def test_quota_error_view_is_friendly_and_preserves_data(self, mocked_generate):
        mocked_generate.side_effect = GeminiQuotaExceededError("technical quota detail")
        client = HttpClient()
        client.force_login(self.reception)
        response = client.post(
            reverse("ai_generate_suggestions", args=[self.note.pk]), follow=True
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "alcanzó temporalmente su límite de uso")
        self.assertNotContains(response, "technical quota detail")
        self.assertTrue(NotaCredito.objects.filter(pk=self.note.pk).exists())

    @patch("credit_notes.ai_services._call_gemini")
    def test_multiple_suggestions_use_one_consolidated_call(self, mocked_call):
        self.add_document()

        def response(_prompt, schema_model, **_kwargs):
            return schema_model(
                sugerencias=[
                    {
                        "campo": "estado_fuente",
                        "valor_sugerido": "VIGENTE",
                        "confianza": 0.9,
                        "fuente": "Respaldo",
                        "evidencia": "Estado indicado.",
                    },
                    {
                        "campo": "saldo_disponible",
                        "valor_sugerido": "950.00",
                        "confianza": 0.8,
                        "fuente": "Respaldo",
                        "evidencia": "Saldo indicado.",
                    },
                ]
            )

        mocked_call.side_effect = response
        suggestions = generar_sugerencias_nota(self.note, self.reception)
        self.assertEqual(len(suggestions), 2)
        mocked_call.assert_called_once()
        prompt = mocked_call.call_args.args[0]
        self.assertLess(len(prompt), 5000)
        self.assertNotIn("Reglas obligatorias para la respuesta", prompt)

    @patch("credit_notes.gemini_service._get_gemini_client")
    def test_suggestion_schema_rejects_items_without_values(self, mocked_client):
        mocked_client.return_value.interactions.create.return_value = SimpleNamespace(
            output_text='{"sugerencias":[{"campo":"estado_fuente"}]}'
        )

        with self.assertRaises(GeminiInvalidResponseError):
            generar_sugerencias_nota(self.note, self.reception)

        self.assertFalse(SugerenciaIA.objects.filter(nota=self.note).exists())

    def _create_suggestion(self, field, value):
        return SugerenciaIA.objects.create(
            nota=self.note,
            campo=field,
            valor_actual=str(getattr(self.note, field, "") or ""),
            valor_sugerido=value,
            confianza=Decimal("0.80"),
            fuente="Documento de prueba",
            evidencia="Valor identificado en el respaldo.",
            generada_por_modelo="gemini-test",
        )

    def test_accept_all_suggestions_applies_every_pending_value(self):
        self._create_suggestion("estado_fuente", "VIGENTE")
        self._create_suggestion("minimo_recibir", "925.00")
        client = HttpClient()
        client.force_login(self.reception)

        response = client.post(
            reverse("suggestions_accept_all", args=[self.note.pk]),
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.note.refresh_from_db()
        self.assertEqual(self.note.estado_fuente, "VIGENTE")
        self.assertEqual(self.note.minimo_recibir, Decimal("925.00"))
        self.assertEqual(
            self.note.sugerencias_ia.filter(
                estado=SugerenciaIA.Estado.ACEPTADA,
                revisada_por=self.reception,
            ).count(),
            2,
        )

    def test_accept_all_suggestions_is_atomic_when_one_value_is_invalid(self):
        self._create_suggestion("saldo_disponible", "975.00")
        self._create_suggestion("fecha_emision", "fecha-invalida")
        original_balance = self.note.saldo_disponible
        client = HttpClient()
        client.force_login(self.reception)

        response = client.post(
            reverse("suggestions_accept_all", args=[self.note.pk]),
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.note.refresh_from_db()
        self.assertEqual(self.note.saldo_disponible, original_balance)
        self.assertEqual(
            self.note.sugerencias_ia.filter(
                estado=SugerenciaIA.Estado.PENDIENTE
            ).count(),
            2,
        )

    def test_reject_all_suggestions_preserves_note_values(self):
        self._create_suggestion("estado_fuente", "VIGENTE")
        self._create_suggestion("minimo_recibir", "925.00")
        original_minimum = self.note.minimo_recibir
        client = HttpClient()
        client.force_login(self.reception)

        response = client.post(
            reverse("suggestions_reject_all", args=[self.note.pk]),
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.note.refresh_from_db()
        self.assertEqual(self.note.minimo_recibir, original_minimum)
        self.assertEqual(
            self.note.sugerencias_ia.filter(
                estado=SugerenciaIA.Estado.RECHAZADA,
                revisada_por=self.reception,
            ).count(),
            2,
        )
