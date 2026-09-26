import datetime

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from . import avisos as avisos_correo
from . import calendario as cal
from .integracion import nombre_de_usuario
from .models import AjusteDias, Configuracion, Empleado, Movimiento, RangoAntiguedad, Solicitud, Tipo, UmbralSede

VACACIONES = Solicitud.TipoSolicitud.VACACIONES
ECONOMICO = Solicitud.TipoSolicitud.ECONOMICO
MOTIVO_MINIMO = 5


def _mov(empleado, accion, usuario, *, solicitud=None, texto="", datos=None):
    return Movimiento.objects.create(
        empleado=empleado, solicitud=solicitud, accion=accion, usuario=usuario, usuario_nombre=nombre_de_usuario(usuario),
        texto=texto, datos=datos or {},
    )


# ---- Saldos -------------------------------------------------------------------------------------------------------

def dias_de_tabla(empleado, anio, periodo):
    """Días de vacaciones que marca la tabla por antigüedad (a la fecha en que inicia el periodo)."""
    inicio, _ = cal.limites_periodo(anio, periodo)
    anios = cal.anios_de_antiguedad(empleado.fecha_ingreso, inicio)
    rango = RangoAntiguedad.objects.filter(tipo=empleado.tipo, desde_anios__lte=anios).order_by("-desde_anios").first()
    return rango.dias(periodo) if rango else 0


def dias_asignados(empleado, tipo, anio, periodo):
    if tipo == ECONOMICO:
        return Configuracion.obtener().dias_economicos(periodo) if empleado.es_sindicalizado else 0
    ajuste = empleado.ajustes.filter(anio=anio, periodo=periodo).first()
    return ajuste.dias if ajuste else dias_de_tabla(empleado, anio, periodo)


def dias_usados(empleado, tipo, anio, periodo, excluir=None):
    consulta = empleado.solicitudes.filter(tipo=tipo, anio=anio, periodo=periodo, estatus=Solicitud.Estatus.ACTIVA)
    if excluir is not None:
        consulta = consulta.exclude(pk=excluir.pk)
    return consulta.aggregate(total=Sum("dias"))["total"] or 0


def saldos(empleado, anio):
    """Renglones por tipo y periodo: asignados, usados y disponibles. Los días no usados se pierden al terminar el periodo."""
    filas = []
    tipos = [(VACACIONES, "Vacaciones")] + ([(ECONOMICO, "Días económicos")] if empleado.es_sindicalizado else [])
    for tipo, etiqueta in tipos:
        for periodo in (1, 2):
            asignados = dias_asignados(empleado, tipo, anio, periodo)
            usados = dias_usados(empleado, tipo, anio, periodo)
            inicio, fin = cal.limites_periodo(anio, periodo)
            filas.append({
                "tipo": tipo, "etiqueta": etiqueta, "periodo": periodo, "nombre_periodo": cal.NOMBRES_PERIODO[periodo],
                "inicio": inicio, "fin": fin, "asignados": asignados, "usados": usados, "disponibles": max(0, asignados - usados),
                "excedido": usados > asignados,
            })
    return filas


# ---- Cobertura ----------------------------------------------------------------------------------------------------

def minimo_de_sede(sede_uuid):
    umbral = UmbralSede.objects.filter(sede_uuid=sede_uuid).first() if sede_uuid else None
    return umbral.minimo if umbral else 1


def cobertura(sede_uuid, fechas):
    """Por cada fecha hábil: quién está fuera, cuántos quedan presentes y el mínimo de la sede."""
    if not sede_uuid:
        return []
    personal = list(Empleado.objects.filter(sede_uuid=sede_uuid, is_active=True).select_related("usuario"))
    if not personal:
        return []
    minimo = minimo_de_sede(sede_uuid)
    inicio, fin = min(fechas), max(fechas)
    solicitudes = list(
        Solicitud.objects.filter(
            empleado__in=personal, estatus=Solicitud.Estatus.ACTIVA, fecha_inicio__lte=fin, fecha_fin__gte=inicio,
        ).select_related("empleado__usuario")
    )
    resultado = []
    for fecha in sorted(set(fechas)):
        if not cal.es_habil(fecha):
            continue
        fuera = {}
        for s in solicitudes:
            if s.fecha_inicio <= fecha <= s.fecha_fin:
                fuera[s.empleado_id] = s
        resultado.append({
            "fecha": fecha, "total": len(personal), "presentes": len(personal) - len(fuera), "minimo": minimo,
            "bajo": len(personal) - len(fuera) < minimo,
            "fuera": [{"nombre": s.empleado.nombre, "tipo": s.tipo, "validado": s.validado} for s in fuera.values()],
        })
    return resultado


# ---- Solicitudes --------------------------------------------------------------------------------------------------

def _calcular_dias(empleado, tipo, inicio, fin):
    if tipo == ECONOMICO:
        if not empleado.es_sindicalizado:
            raise ValidationError("Los días económicos son solo para el personal sindicalizado.")
        fechas = cal.rango(inicio, fin)
        if any(not cal.es_habil(f) for f in fechas):
            raise ValidationError("Los días económicos no pueden ser sábado ni domingo.")
        return len(fechas)
    habiles = cal.dias_habiles(inicio, fin)
    if not habiles:
        raise ValidationError("Las vacaciones se cuentan de lunes a viernes: el rango no incluye ningún día hábil.")
    return len(habiles)


@transaction.atomic
def crear_solicitud(empleado, *, usuario, tipo, fecha_inicio, fecha_fin, comentarios="", avisar=True):
    """Registra la solicitud y descuenta el saldo. Devuelve (solicitud, avisos); bajar del mínimo de la sede solo avisa."""
    empleado = Empleado.objects.select_for_update().select_related("usuario").get(pk=empleado.pk)
    if not empleado.is_active:
        raise ValidationError("El empleado no está activo.")
    if tipo not in Solicitud.TipoSolicitud.values:
        raise ValidationError("Elija el tipo de solicitud.")
    if fecha_fin < fecha_inicio:
        raise ValidationError("La fecha final no puede ser anterior a la inicial.")
    anio, periodo = cal.periodo_de(fecha_inicio)
    if cal.periodo_de(fecha_fin) != (anio, periodo):
        raise ValidationError("La solicitud debe quedar dentro de un mismo periodo (enero a junio o julio a diciembre): divídala en dos.")
    dias = _calcular_dias(empleado, tipo, fecha_inicio, fecha_fin)
    traslape = empleado.solicitudes.filter(
        estatus=Solicitud.Estatus.ACTIVA, fecha_inicio__lte=fecha_fin, fecha_fin__gte=fecha_inicio,
    ).first()
    if traslape:
        raise ValidationError(f"Ya tiene una solicitud del {traslape.fecha_inicio:%d/%m/%Y} al {traslape.fecha_fin:%d/%m/%Y} que se empalma.")
    asignados = dias_asignados(empleado, tipo, anio, periodo)
    disponibles = asignados - dias_usados(empleado, tipo, anio, periodo)
    if dias > disponibles:
        raise ValidationError(
            f"La solicitud descuenta {dias} día(s) y en el {cal.NOMBRES_PERIODO[periodo]} solo le quedan {max(0, disponibles)} de {asignados}."
        )
    solicitud = Solicitud.objects.create(
        empleado=empleado, tipo=tipo, anio=anio, periodo=periodo, fecha_inicio=fecha_inicio, fecha_fin=fecha_fin, dias=dias,
        comentarios=(comentarios or "").strip(), sede_uuid=empleado.sede_uuid, sede_nombre=empleado.sede_nombre,
    )
    bajo = [c for c in cobertura(empleado.sede_uuid, cal.rango(fecha_inicio, fecha_fin)) if c["bajo"]]
    solicitud.bajo_umbral = [{"fecha": c["fecha"].isoformat(), "presentes": c["presentes"], "minimo": c["minimo"]} for c in bajo]
    solicitud.save(update_fields=["bajo_umbral"])
    _mov(empleado, "solicitud", usuario, solicitud=solicitud, datos={
        "tipo": solicitud.get_tipo_display(), "del": fecha_inicio.isoformat(), "al": fecha_fin.isoformat(), "dias": dias,
        "bajo_umbral": len(bajo),
    })
    if avisar:
        avisos_correo.bajo_minimo(solicitud, [{"fecha": c["fecha"], "presentes": c["presentes"], "minimo": c["minimo"]} for c in bajo], actor=usuario)
    avisos = []
    if bajo:
        primeras = ", ".join(f"{c['fecha']:%d/%m} ({c['presentes']} de mínimo {c['minimo']})" for c in bajo[:5])
        avisos.append(
            f"Ojo: en {empleado.sede_nombre or 'su sede'} el personal presente queda por debajo del mínimo en {len(bajo)} día(s): {primeras}"
            + ("…" if len(bajo) > 5 else "") + ". La solicitud se registró; conviene coordinar la cobertura."
        )
    return solicitud, avisos


@transaction.atomic
def cancelar_solicitud(solicitud, *, usuario, motivo, es_control=False):
    solicitud = Solicitud.objects.select_for_update().select_related("empleado").get(pk=solicitud.pk)
    motivo = (motivo or "").strip()
    if not solicitud.activa:
        raise ValidationError("La solicitud ya está cancelada.")
    if solicitud.validado and not es_control:
        raise ValidationError("La solicitud ya fue validada: pídale a control que la cancele.")
    if len(motivo) < MOTIVO_MINIMO:
        raise ValidationError(f"Indique el motivo (mínimo {MOTIVO_MINIMO} caracteres).")
    solicitud.estatus, solicitud.motivo_cancelacion = Solicitud.Estatus.CANCELADA, motivo
    solicitud.save(update_fields=["estatus", "motivo_cancelacion", "updated_at"])
    _mov(solicitud.empleado, "cancelacion", usuario, solicitud=solicitud, texto=motivo)
    return solicitud


@transaction.atomic
def validar_solicitud(solicitud, *, usuario, validado=True):
    """Check de «validado». Es un control: no aprueba ni cambia el saldo (la aprobación queda para una fase posterior)."""
    solicitud = Solicitud.objects.select_for_update().select_related("empleado").get(pk=solicitud.pk)
    if not solicitud.activa:
        raise ValidationError("No se puede validar una solicitud cancelada.")
    if solicitud.validado == validado:
        raise ValidationError("La solicitud ya está " + ("validada." if validado else "sin validar."))
    solicitud.validado = validado
    solicitud.validado_por = usuario if validado else None
    solicitud.validado_en = timezone.now() if validado else None
    solicitud.save(update_fields=["validado", "validado_por", "validado_en", "updated_at"])
    _mov(solicitud.empleado, "validacion" if validado else "quitar_validacion", usuario, solicitud=solicitud)
    return solicitud


# ---- Empleados y configuración --------------------------------------------------------------------------------------

@transaction.atomic
def guardar_empleado(*, usuario_actor, empleado=None, usuario=None, tipo, fecha_ingreso, sede_uuid=None, sede_nombre="", activo=True):
    if fecha_ingreso > timezone.localdate():
        raise ValidationError("La fecha de ingreso no puede ser futura.")
    if tipo not in Tipo.values:
        raise ValidationError("Elija el tipo de personal.")
    if empleado is None:
        if usuario is None:
            raise ValidationError("Elija el usuario.")
        if Empleado.objects.filter(usuario=usuario).exists():
            raise ValidationError("Ese usuario ya está dado de alta como empleado.")
        empleado = Empleado(usuario=usuario)
    empleado.tipo, empleado.fecha_ingreso, empleado.is_active = tipo, fecha_ingreso, activo
    empleado.sede_uuid, empleado.sede_nombre = sede_uuid, sede_nombre if sede_uuid else ""
    nuevo = empleado._state.adding
    empleado.save()
    _mov(empleado, "alta" if nuevo else "cambio", usuario_actor, datos={"tipo": tipo, "ingreso": fecha_ingreso.isoformat(), "sede": empleado.sede_nombre})
    return empleado


@transaction.atomic
def ajustar_dias(empleado, *, usuario, anio, periodo, dias):
    """Fija los días de vacaciones de un empleado en un periodo, cuando difieren de la tabla por antigüedad."""
    if periodo not in (1, 2):
        raise ValidationError("Periodo no válido.")
    if dias < 0 or dias > 60:
        raise ValidationError("Los días deben estar entre 0 y 60.")
    usados = dias_usados(empleado, VACACIONES, anio, periodo)
    if dias < usados:
        raise ValidationError(f"Ya tiene {usados} día(s) solicitados en ese periodo: no puede fijarse por debajo.")
    anterior = dias_asignados(empleado, VACACIONES, anio, periodo)
    AjusteDias.objects.update_or_create(empleado=empleado, anio=anio, periodo=periodo, defaults={"dias": dias})
    _mov(empleado, "ajuste_dias", usuario, datos={"anio": anio, "periodo": periodo, "antes": anterior, "despues": dias})


def quitar_ajuste(empleado, *, usuario, anio, periodo):
    borrados, _ = AjusteDias.objects.filter(empleado=empleado, anio=anio, periodo=periodo).delete()
    if borrados:
        _mov(empleado, "quitar_ajuste", usuario, datos={"anio": anio, "periodo": periodo})


# ---- Calendario del mes ---------------------------------------------------------------------------------------------

def calendario_mes(anio, mes, sede_uuid=None):
    """Semanas del mes con, por día hábil, quién está fuera y en qué sedes el personal presente queda bajo el mínimo."""
    import calendar as pycal

    primer, ultimo = datetime.date(anio, mes, 1), datetime.date(anio, mes, pycal.monthrange(anio, mes)[1])
    personal = Empleado.objects.filter(is_active=True).select_related("usuario")
    if sede_uuid:
        personal = personal.filter(sede_uuid=sede_uuid)
    personal = list(personal)
    por_sede = {}
    for e in personal:
        por_sede.setdefault((e.sede_uuid, e.sede_nombre or "Sin sede"), []).append(e)
    minimos = {u.sede_uuid: u.minimo for u in UmbralSede.objects.all()}
    solicitudes = list(
        Solicitud.objects.filter(
            empleado__in=personal, estatus=Solicitud.Estatus.ACTIVA, fecha_inicio__lte=ultimo, fecha_fin__gte=primer,
        ).select_related("empleado__usuario")
    )
    semanas = []
    for semana in pycal.Calendar(firstweekday=0).monthdatescalendar(anio, mes):
        fila = []
        for fecha in semana:
            fuera = [s for s in solicitudes if s.fecha_inicio <= fecha <= s.fecha_fin] if cal.es_habil(fecha) else []
            fuera_ids = {s.empleado_id for s in fuera}
            bajo = []
            for (sede, nombre), gente in por_sede.items():
                presentes = len([e for e in gente if e.pk not in fuera_ids])
                if cal.es_habil(fecha) and presentes < minimos.get(sede, 1) and len(gente) != presentes:
                    bajo.append({"sede": nombre, "presentes": presentes, "minimo": minimos.get(sede, 1)})
            fila.append({
                "fecha": fecha, "en_mes": fecha.month == mes, "habil": cal.es_habil(fecha),
                "fuera": [{"nombre": s.empleado.nombre, "tipo": s.tipo, "validado": s.validado, "sede": s.sede_nombre} for s in fuera],
                "bajo": bajo,
            })
        semanas.append(fila)
    return semanas
