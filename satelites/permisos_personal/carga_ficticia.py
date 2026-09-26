"""Carga datos FICTICIOS para probar el módulo (configuración, tabla por antigüedad, sedes, empleados y unas solicitudes).

Es repetible: actualiza lo que ya existe y no duplica. Las personas son usuarios de prueba sin contraseña ni acceso.
"""
import datetime
import json
from pathlib import Path

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from . import calendario as cal
from . import services
from .integracion import sedes_del_core, usuario_de_prueba
from .models import AjusteDias, Configuracion, Empleado, RangoAntiguedad, Solicitud, UmbralSede

ARCHIVO = Path(__file__).resolve().parent / "datos" / "ficticios.json"


def leer(ruta=None):
    return json.loads(Path(ruta or ARCHIVO).read_text(encoding="utf-8"))


@transaction.atomic
def cargar(datos, *, aplicar=False):
    """Devuelve un resumen. Sin `aplicar` se hace todo y se revierte, para que la simulación muestre lo mismo que pasaría."""
    resumen = {"empleados": 0, "rangos": 0, "umbrales": 0, "ajustes": 0, "solicitudes": 0, "avisos": []}
    sedes = {nombre: pk for pk, nombre in sedes_del_core()}
    config = Configuracion.obtener()
    for campo, valor in datos.get("configuracion", {}).items():
        setattr(config, campo, valor)
    config.save()
    for fila in datos.get("antiguedad", []):
        RangoAntiguedad.objects.update_or_create(
            tipo=fila["tipo"], desde_anios=fila["desde_anios"], defaults={"dias_p1": fila["dias_p1"], "dias_p2": fila["dias_p2"]},
        )
        resumen["rangos"] += 1
    for nombre, minimo in datos.get("umbrales", {}).items():
        if nombre in sedes:
            UmbralSede.objects.update_or_create(sede_uuid=sedes[nombre], defaults={"sede_nombre": nombre, "minimo": minimo})
            resumen["umbrales"] += 1
        else:
            resumen["avisos"].append(f"La sede «{nombre}» no existe en el sistema: se omitió su mínimo.")
    por_correo = {}
    for fila in datos.get("empleados", []):
        usuario = usuario_de_prueba(fila["correo"], fila["nombre"], fila["apellidos"])
        sede = sedes.get(fila.get("sede", ""))
        if fila.get("sede") and sede is None:
            resumen["avisos"].append(f"La sede «{fila['sede']}» no existe: {fila['nombre']} se cargó sin sede.")
        empleado, _ = Empleado.objects.update_or_create(usuario=usuario, defaults={
            "tipo": fila["tipo"], "fecha_ingreso": datetime.date.fromisoformat(fila["ingreso"]),
            "sede_uuid": sede, "sede_nombre": fila.get("sede", "") if sede else "", "is_active": True,
        })
        por_correo[fila["correo"]] = empleado
        resumen["empleados"] += 1
        for ajuste in fila.get("ajustes", []):
            AjusteDias.objects.update_or_create(empleado=empleado, anio=ajuste["anio"], periodo=ajuste["periodo"], defaults={"dias": ajuste["dias"]})
            resumen["ajustes"] += 1
    hoy = timezone.localdate()
    for fila in datos.get("solicitudes", []):
        empleado = por_correo.get(fila["correo"]) or Empleado.objects.filter(usuario__email=fila["correo"]).first()
        if empleado is None:
            continue
        inicio = hoy + datetime.timedelta(days=fila["desde_hoy"])
        while not cal.es_habil(inicio):
            inicio += datetime.timedelta(days=1)
        fin = inicio + datetime.timedelta(days=fila["dias_naturales"] - 1)
        if fila["tipo"] == "economico":
            fin = inicio
        if empleado.solicitudes.filter(estatus=Solicitud.Estatus.ACTIVA, comentarios=fila.get("comentarios", ""), fecha_inicio=inicio).exists():
            continue
        try:
            services.crear_solicitud(empleado, usuario=empleado.usuario, tipo=fila["tipo"], fecha_inicio=inicio, fecha_fin=fin, comentarios=fila.get("comentarios", ""))
            resumen["solicitudes"] += 1
        except ValidationError as error:
            resumen["avisos"].append(f"Solicitud de {empleado.nombre} omitida: {'; '.join(error.messages)}")
    if not aplicar:
        transaction.set_rollback(True)
    return resumen
