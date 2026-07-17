from django.db import migrations, models
from django.utils import timezone


def close_duplicate_active_runs(apps, schema_editor):
    execution = apps.get_model("credit_notes", "EjecucionAgente")
    seen = set()
    active = execution.objects.filter(
        estado__in=["EJECUTANDO", "ESPERANDO_HUMANO"]
    ).order_by("nota_id", "operador_id", "-iniciada_en")
    for run in active.iterator():
        key = (run.nota_id, run.operador_id)
        if key in seen:
            run.estado = "ERROR_CONTROLADO"
            run.error_amigable = (
                "Ejecución anterior cerrada al consolidar solicitudes duplicadas."
            )
            run.finalizada_en = timezone.now()
            run.save(
                update_fields=["estado", "error_amigable", "finalizada_en"]
            )
        else:
            seen.add(key)


class Migration(migrations.Migration):
    dependencies = [("credit_notes", "0004_agentic_rag")]

    operations = [
        migrations.AddField(
            model_name="operacionidempotente",
            name="actualizada_en",
            field=models.DateTimeField(auto_now=True),
        ),
        migrations.AddField(
            model_name="operacionidempotente",
            name="error_tipo",
            field=models.CharField(blank=True, max_length=40),
        ),
        migrations.AddField(
            model_name="operacionidempotente",
            name="expira_en",
            field=models.DateTimeField(blank=True, db_index=True, null=True),
        ),
        migrations.AddField(
            model_name="operacionidempotente",
            name="intentos",
            field=models.PositiveSmallIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="operacionidempotente",
            name="resultado",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.RunPython(close_duplicate_active_runs, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="ejecucionagente",
            constraint=models.UniqueConstraint(
                condition=models.Q(
                    ("estado__in", ["EJECUTANDO", "ESPERANDO_HUMANO"])
                ),
                fields=("nota", "operador"),
                name="unique_active_agent_run",
            ),
        ),
    ]
