"""Carga datos FICTICIOS para probar el módulo: técnicos de prueba y varios eventos (pasados, en curso y por venir).

Es repetible: no duplica (un evento se reconoce por su nombre). Las fechas son relativas a hoy.
"""
import datetime
import json
from pathlib import Path

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from . import services
from .integracion import usuario_de_prueba
from .models import Evento

ARCHIVO = Path(__file__).resolve().parent / "datos" / "ficticios.json"


def leer(ruta=None):
    return json.loads(Path(ruta or ARCHIVO).read_text(encoding="utf-8"))


def _momento(base, dias, hora):
    h, m = (int(x) for x in hora.split(":"))
    return timezone.make_aware(datetime.datetime.combine(base + datetime.timedelta(days=dias), datetime.time(h, m)))


@transaction.atomic
def cargar(datos, *, aplicar=False):
    resumen = {"tecnicos": 0, "eventos": 0, "asignaciones": 0, "avisos": []}
    tecnicos = {}
    for fila in datos.get("tecnicos", []):
        tecnicos[fila["correo"]] = usuario_de_prueba(fila["correo"], fila["nombre"], fila["apellidos"])
        resumen["tecnicos"] += 1
    hoy = timezone.localdate()
    for fila in datos.get("eventos", []):
        if Evento.objects.filter(nombre=fila["nombre"]).exists():
            continue
        inicio, fin = _momento(hoy, fila["dia"], fila["inicio"]), _momento(hoy, fila["dia"] + fila.get("dias_extra", 0), fila["fin"])
        evento = services.crear_evento(
            usuario=None, nombre=fila["nombre"], lugar=fila["lugar"], inicio=inicio, fin=fin,
            descripcion=fila.get("descripcion", ""), ticket=fila.get("ticket", ""),
        )
        resumen["eventos"] += 1
        try:
            for a in fila.get("tecnicos", []):
                desde = _momento(hoy, a.get("dia", fila["dia"]), a["desde"]) if a.get("desde") else None
                hasta = _momento(hoy, a.get("dia", fila["dia"]), a["hasta"]) if a.get("hasta") else None
                services.asignar_tecnico(evento, usuario=None, tecnico=tecnicos[a["correo"]], desde=desde, hasta=hasta, nota=a.get("nota", ""), avisar=False)
                resumen["asignaciones"] += 1
            for referencia, nota in fila.get("vales", []):
                services.vincular_vale(evento, usuario=None, referencia=referencia, nota=nota)
            for tipo, descripcion, estado in fila.get("telefonia", []):
                tramite = services.agregar_tramite(evento, usuario=None, tipo=tipo, descripcion=descripcion)
                services.cambiar_estado_tramite(tramite, usuario=None, estado=estado)
            for texto in fila.get("notas", []):
                services.agregar_nota(evento, usuario=None, texto=texto)
            estado = fila.get("estado", "programado")
            if estado in ("en_curso", "concluido"):
                services.iniciar_evento(evento, usuario=None)
            if estado == "concluido":
                services.concluir_evento(evento, usuario=None, notas=fila.get("cierre", ""))
        except (ValidationError, KeyError) as error:
            resumen["avisos"].append(f"Evento «{fila['nombre']}»: {getattr(error, 'messages', error)}")
    if not aplicar:
        transaction.set_rollback(True)
    return resumen
