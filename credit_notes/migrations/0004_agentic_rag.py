import django.db.models.deletion
import pgvector.django
import uuid
from django.conf import settings
from django.db import migrations, models


def enable_vector(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        with schema_editor.connection.cursor() as cursor:
            cursor.execute("CREATE EXTENSION IF NOT EXISTS vector")


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("credit_notes", "0003_negotiation_versions"),
    ]
    operations = [
        migrations.RunPython(enable_vector, migrations.RunPython.noop),
        migrations.CreateModel(
            name="EjecucionAgente",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("estado", models.CharField(choices=[("EJECUTANDO", "Ejecutando"), ("ESPERANDO_HUMANO", "Esperando revision humana"), ("COMPLETADA", "Completada"), ("ERROR_CONTROLADO", "Error controlado")], db_index=True, default="EJECUTANDO", max_length=24)),
                ("etapa", models.CharField(default="supervisor", max_length=80)),
                ("nodo_pendiente", models.CharField(blank=True, max_length=80)),
                ("estado_compartido", models.JSONField(default=dict)),
                ("decisiones_humanas", models.JSONField(blank=True, default=list)),
                ("error_amigable", models.CharField(blank=True, max_length=300)),
                ("iniciada_en", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("actualizada_en", models.DateTimeField(auto_now=True)),
                ("finalizada_en", models.DateTimeField(blank=True, null=True)),
                ("nota", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="ejecuciones_agentes", to="credit_notes.notacredito")),
                ("operador", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="ejecuciones_agentes", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["-iniciada_en"]},
        ),
        migrations.CreateModel(
            name="EventoAgente",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("agente", models.CharField(db_index=True, max_length=80)),
                ("estado", models.CharField(choices=[("INICIADO", "Iniciado"), ("COMPLETADO", "Completado"), ("ERROR", "Error controlado")], max_length=12)),
                ("resumen", models.CharField(max_length=300)),
                ("metadatos", models.JSONField(blank=True, default=dict)),
                ("creado_en", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("ejecucion", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="eventos", to="credit_notes.ejecucionagente")),
            ],
            options={"ordering": ["creado_en"]},
        ),
        migrations.CreateModel(
            name="MemoriaAgente",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("ambito", models.CharField(choices=[("NOTA", "Nota"), ("CLIENTE", "Cliente"), ("OPERADOR", "Operador")], max_length=12)),
                ("categoria", models.CharField(db_index=True, max_length=80)),
                ("contenido", models.JSONField(default=dict)),
                ("vigente", models.BooleanField(db_index=True, default=True)),
                ("creada_en", models.DateTimeField(auto_now_add=True)),
                ("actualizada_en", models.DateTimeField(auto_now=True)),
                ("cliente", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="memorias_agente", to="credit_notes.cliente")),
                ("nota", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="memorias_agente", to="credit_notes.notacredito")),
                ("operador", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="memorias_agente", to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name="FragmentoDocumento",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("indice", models.PositiveIntegerField()),
                ("seccion", models.CharField(blank=True, max_length=120)),
                ("texto", models.TextField()),
                ("texto_hash", models.CharField(db_index=True, max_length=64)),
                ("fuente", models.CharField(max_length=200)),
                ("tipo_documento", models.CharField(max_length=30)),
                ("embedding", pgvector.django.VectorField(dimensions=768)),
                ("modelo_embedding", models.CharField(max_length=100)),
                ("creado_en", models.DateTimeField(auto_now_add=True)),
                ("cliente", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="fragmentos_rag", to="credit_notes.cliente")),
                ("documento", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="fragmentos", to="credit_notes.documentorespaldo")),
                ("nota", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="fragmentos_rag", to="credit_notes.notacredito")),
            ],
            options={"ordering": ["documento", "indice"]},
        ),
        migrations.AddConstraint(model_name="fragmentodocumento", constraint=models.UniqueConstraint(fields=("documento", "texto_hash"), name="unique_chunk_hash_per_document")),
        migrations.AddIndex(model_name="ejecucionagente", index=models.Index(fields=["nota", "estado", "iniciada_en"], name="credit_note_nota_id_335f05_idx")),
        migrations.AddIndex(model_name="ejecucionagente", index=models.Index(fields=["operador", "estado"], name="credit_note_operado_b1316a_idx")),
        migrations.AddIndex(model_name="eventoagente", index=models.Index(fields=["ejecucion", "creado_en"], name="credit_note_ejecuci_5f88c1_idx")),
        migrations.AddIndex(model_name="memoriaagente", index=models.Index(fields=["operador", "ambito", "vigente"], name="credit_note_operado_a29c75_idx")),
        migrations.AddIndex(model_name="memoriaagente", index=models.Index(fields=["nota", "categoria"], name="credit_note_nota_id_029fa7_idx")),
        migrations.AddIndex(model_name="memoriaagente", index=models.Index(fields=["cliente", "categoria"], name="credit_note_cliente_62c49a_idx")),
        migrations.AddIndex(model_name="fragmentodocumento", index=models.Index(fields=["nota", "tipo_documento"], name="credit_note_nota_id_b775ae_idx")),
        migrations.AddIndex(model_name="fragmentodocumento", index=models.Index(fields=["cliente", "creado_en"], name="credit_note_cliente_a47fde_idx")),
    ]
