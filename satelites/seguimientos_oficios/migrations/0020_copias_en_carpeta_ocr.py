import os

from django.db import migrations

from satelites.seguimientos_oficios.storage import almacen, ruta_copia_ocr


def mover_copias(apps, schema_editor):
    """Pasa las copias con texto que quedaron junto al original a la carpeta `ocr/` de su misma carpeta."""
    OCR = apps.get_model("seguimientos_oficios", "AdjuntoOCR")
    almacen_ = almacen()
    for vieja in list(OCR.objects.exclude(ruta_buscable="").values_list("ruta_buscable", flat=True).distinct()):
        if "/ocr/" in f"/{vieja}":
            continue
        registro = OCR.objects.filter(ruta_buscable=vieja).select_related("adjunto").first()
        nueva = ruta_copia_ocr(registro.adjunto.ruta)
        if not almacen_.exists(vieja):
            OCR.objects.filter(ruta_buscable=vieja).update(ruta_buscable="")
            continue
        destino = almacen_.path(nueva)
        os.makedirs(os.path.dirname(destino), exist_ok=True)
        os.replace(almacen_.path(vieja), destino)
        OCR.objects.filter(ruta_buscable=vieja).update(ruta_buscable=nueva)


class Migration(migrations.Migration):
    dependencies = [("seguimientos_oficios", "0019_copia_buscable")]
    operations = [migrations.RunPython(mover_copias, migrations.RunPython.noop)]
