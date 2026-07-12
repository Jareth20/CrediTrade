from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("credit_notes", "0001_initial"), migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [
        migrations.AddField(model_name=name, name="eliminado_en", field=models.DateTimeField(blank=True, db_index=True, null=True))
        for name in ("cliente", "notacredito", "validacionnota", "ordennegociacion")
    ] + [
        migrations.AddField(model_name=name, name="motivo_eliminacion", field=models.CharField(blank=True, max_length=300))
        for name in ("cliente", "notacredito", "validacionnota", "ordennegociacion")
    ] + [
        migrations.AddField(model_name="cliente", name="eliminado_por", field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="clientes_eliminados", to=settings.AUTH_USER_MODEL)),
        migrations.AddField(model_name="notacredito", name="eliminado_por", field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="expedientes_eliminados", to=settings.AUTH_USER_MODEL)),
        migrations.AddField(model_name="validacionnota", name="actualizado_en", field=models.DateTimeField(auto_now=True)),
        migrations.AddField(model_name="validacionnota", name="eliminado_por", field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="validaciones_eliminadas", to=settings.AUTH_USER_MODEL)),
        migrations.AddField(model_name="ordennegociacion", name="eliminado_por", field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="negociaciones_eliminadas", to=settings.AUTH_USER_MODEL)),
        migrations.CreateModel(name="OperacionIdempotente", fields=[("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")), ("clave", models.CharField(max_length=255, unique=True)), ("tipo", models.CharField(db_index=True, max_length=80)), ("creada_en", models.DateTimeField(auto_now_add=True)), ("completada_en", models.DateTimeField(blank=True, null=True)), ("resultado_id", models.CharField(blank=True, max_length=80))]),
    ]
