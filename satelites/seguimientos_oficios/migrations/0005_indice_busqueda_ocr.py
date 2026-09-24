from django.contrib.postgres.indexes import GinIndex
from django.contrib.postgres.search import SearchVector
from django.db import migrations

INDICE = GinIndex(SearchVector("texto", config="spanish"), name="oficios_ocr_fts_idx")


def crear(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.add_index(apps.get_model("seguimientos_oficios", "AdjuntoOCR"), INDICE)


def quitar(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.remove_index(apps.get_model("seguimientos_oficios", "AdjuntoOCR"), INDICE)


class Migration(migrations.Migration):
    dependencies = [("seguimientos_oficios", "0004_ocr")]
    operations = [migrations.RunPython(crear, quitar)]
