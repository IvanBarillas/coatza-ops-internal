from django.db import migrations


def borrar_ocr_de_acuses(apps, schema_editor):
    apps.get_model("seguimientos_oficios", "AdjuntoOCR").objects.filter(adjunto__rol="evidencia").delete()


class Migration(migrations.Migration):
    dependencies = [("seguimientos_oficios", "0017_quitar_usuario_gestor")]
    operations = [migrations.RunPython(borrar_ocr_de_acuses, migrations.RunPython.noop)]
