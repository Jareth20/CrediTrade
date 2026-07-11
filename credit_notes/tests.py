from datetime import date
from decimal import Decimal
from unittest.mock import patch

from django.test import Client as HttpClient, TestCase, override_settings
from django.urls import reverse

from accounts.models import Operador
from credit_notes.ai_services import (
    GeminiServiceError,
    generar_reporte_negociacion,
    generar_sugerencias_nota,
)
from credit_notes.models import (
    Cliente,
    DocumentoRespaldo,
    NotaCredito,
    OrdenNegociacion,
    RegistroSimuladoTitulo,
    ReporteIA,
    SolicitudAprobacion,
)
from credit_notes.services import enviar_a_validacion, ejecutar_validacion_simulada


@override_settings(
    SECURE_SSL_REDIRECT=False,
    GEMINI_API_KEY="test-key",
    GEMINI_MODEL="gemini-test",
)
class WorkflowTests(TestCase):
    def setUp(self):
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

        def fake_call(prompt, schema_model):
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

    @patch("credit_notes.ai_services._call_gemini")
    def test_suggestions_are_saved_only_after_valid_gemini_response(self, mock_call):
        self.add_document()

        def fake_call(prompt, schema_model):
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
