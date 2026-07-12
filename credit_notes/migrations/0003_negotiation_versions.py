from django.db import migrations, models


def populate_contract_snapshots(apps, schema_editor):
    Approval = apps.get_model("credit_notes", "SolicitudAprobacion")
    for approval in Approval.objects.select_related("orden__nota__cliente_vendedor", "orden__comprador"):
        order = approval.orden
        approval.contrato_snapshot = {
            "version": 1,
            "numero_titulo": order.nota.numero_titulo,
            "vendedor": order.nota.cliente_vendedor.nombre_razon_social,
            "comprador": order.comprador.nombre_razon_social,
            "valor_venta": str(order.valor_venta),
            "porcentaje_descuento": str(order.porcentaje_descuento),
            "fecha_propuesta": order.fecha_propuesta.isoformat(),
            "vigencia_hasta": order.vigencia_hasta.isoformat() if order.vigencia_hasta else "",
            "terminos": order.terminos,
            "observaciones": order.observaciones,
        }
        approval.save(update_fields=["contrato_snapshot"])


class Migration(migrations.Migration):
    dependencies = [("credit_notes", "0002_audit_idempotency")]
    operations = [
        migrations.AddField(model_name="ordennegociacion", name="version", field=models.PositiveIntegerField(default=1)),
        migrations.AddField(model_name="solicitudaprobacion", name="version_contrato", field=models.PositiveIntegerField(default=1)),
        migrations.AddField(model_name="solicitudaprobacion", name="contrato_snapshot", field=models.JSONField(blank=True, default=dict)),
        migrations.RunPython(populate_contract_snapshots, migrations.RunPython.noop),
        migrations.AlterField(model_name="solicitudaprobacion", name="estado", field=models.CharField(choices=[("PENDIENTE", "Pendiente"), ("APROBADA", "Aprobada"), ("RECHAZADA", "Rechazada"), ("EXPIRADA", "Reemplazada por una nueva versión")], db_index=True, default="PENDIENTE", max_length=10)),
        migrations.RemoveConstraint(model_name="solicitudaprobacion", name="unique_approval_party_per_order"),
        migrations.AddConstraint(model_name="solicitudaprobacion", constraint=models.UniqueConstraint(fields=("orden", "parte", "version_contrato"), name="unique_approval_party_per_order_version")),
    ]
