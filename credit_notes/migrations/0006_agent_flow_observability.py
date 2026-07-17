from django.db import migrations, models


def assign_event_order(apps, schema_editor):
    Event = apps.get_model("credit_notes", "EventoAgente")
    execution_ids = Event.objects.values_list("ejecucion_id", flat=True).distinct()
    for execution_id in execution_ids.iterator():
        events = Event.objects.filter(ejecucion_id=execution_id).order_by(
            "creado_en", "pk"
        )
        for order, event in enumerate(events.iterator(), start=1):
            Event.objects.filter(pk=event.pk).update(orden=order)


class Migration(migrations.Migration):
    # PostgreSQL no permite agregar la restriccion mientras siguen pendientes
    # los eventos de los triggers generados por assign_event_order(). Al hacer
    # la migracion no atomica, el backfill termina antes del ALTER TABLE.
    atomic = False

    dependencies = [("credit_notes", "0005_gemini_resilience")]

    operations = [
        migrations.AlterModelOptions(
            name="eventoagente",
            options={"ordering": ["orden", "creado_en"]},
        ),
        migrations.AlterField(
            model_name="eventoagente",
            name="estado",
            field=models.CharField(
                choices=[
                    ("INICIADO", "Iniciado"),
                    ("COMPLETADO", "Completado"),
                    ("ERROR", "Error controlado"),
                    ("ESPERANDO_HUMANO", "Esperando revisión humana"),
                    ("REANUDADO", "Reanudado"),
                    ("CANCELADO", "Cancelado"),
                    ("NO_DISPONIBLE", "Servicio no disponible"),
                ],
                max_length=24,
            ),
        ),
        migrations.AddField(model_name="eventoagente", name="orden", field=models.PositiveIntegerField(default=0)),
        migrations.AddField(model_name="eventoagente", name="entrada", field=models.JSONField(blank=True, default=dict)),
        migrations.AddField(model_name="eventoagente", name="salida", field=models.JSONField(blank=True, default=dict)),
        migrations.AddField(model_name="eventoagente", name="cambios", field=models.JSONField(blank=True, default=list)),
        migrations.AddField(model_name="eventoagente", name="fuentes", field=models.JSONField(blank=True, default=list)),
        migrations.AddField(model_name="eventoagente", name="transicion", field=models.CharField(blank=True, max_length=80)),
        migrations.AddField(model_name="eventoagente", name="iniciada_en", field=models.DateTimeField(blank=True, null=True)),
        migrations.AddField(model_name="eventoagente", name="finalizada_en", field=models.DateTimeField(blank=True, null=True)),
        migrations.AddField(model_name="eventoagente", name="duracion_ms", field=models.PositiveIntegerField(blank=True, null=True)),
        migrations.AddField(model_name="eventoagente", name="intento", field=models.PositiveSmallIntegerField(default=1)),
        migrations.AddField(model_name="eventoagente", name="reintentos", field=models.PositiveSmallIntegerField(default=0)),
        migrations.AddField(model_name="eventoagente", name="error_controlado", field=models.CharField(blank=True, max_length=300)),
        migrations.RunPython(assign_event_order, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="eventoagente",
            constraint=models.UniqueConstraint(
                fields=("ejecucion", "orden"), name="unique_agent_event_order"
            ),
        ),
        migrations.AddIndex(
            model_name="eventoagente",
            index=models.Index(
                fields=["ejecucion", "orden"], name="credit_note_exec_order_idx"
            ),
        ),
    ]
