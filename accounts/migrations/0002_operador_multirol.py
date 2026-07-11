from django.db import migrations, models


def copiar_rol_anterior(apps, schema_editor):
    Operador = apps.get_model("accounts", "Operador")
    for operador in Operador.objects.all().iterator():
        operador.puede_recepcionar = operador.tipo_operador == 1
        operador.puede_validar = operador.tipo_operador == 2
        operador.puede_negociar = operador.tipo_operador == 3
        operador.save(
            update_fields=[
                "puede_recepcionar",
                "puede_validar",
                "puede_negociar",
            ]
        )


class Migration(migrations.Migration):
    dependencies = [("accounts", "0001_initial")]

    operations = [
        migrations.AddField(
            model_name="operador",
            name="puede_recepcionar",
            field=models.BooleanField(
                default=False, verbose_name="Operador 1 - Recepcionista"
            ),
        ),
        migrations.AddField(
            model_name="operador",
            name="puede_validar",
            field=models.BooleanField(
                default=False, verbose_name="Operador 2 - Contador"
            ),
        ),
        migrations.AddField(
            model_name="operador",
            name="puede_negociar",
            field=models.BooleanField(
                default=False, verbose_name="Operador 3 - Vendedor"
            ),
        ),
        migrations.RunPython(copiar_rol_anterior, migrations.RunPython.noop),
        migrations.RemoveIndex(
            model_name="operador",
            name="accounts_op_tipo_op_172db3_idx",
        ),
        migrations.RemoveField(
            model_name="operador",
            name="tipo_operador",
        ),
        migrations.AddIndex(
            model_name="operador",
            index=models.Index(
                fields=["is_active", "activo_operativamente"],
                name="operador_activo_idx",
            ),
        ),
    ]
