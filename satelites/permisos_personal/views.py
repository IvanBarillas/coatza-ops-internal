import calendar as pycal
import datetime

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from . import calendario as cal
from . import exportes
from . import selectors as sel
from . import services
from .forms import AjusteForm, ConfiguracionForm, EmpleadoForm, RangoForm, SolicitudForm
from .integracion import proteger_vista, sedes_del_core
from .models import Configuracion, Empleado, RangoAntiguedad, Solicitud, Tipo, UmbralSede
from .selectors import APP_SLUG, permitido

MESES = ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre")


def _menu(request):
    actual = request.resolver_match.view_name if request.resolver_match else ""
    return [
        {"icon": i["icon"], "name": i["name"], "href": reverse(i["url"]), "active": i["url"] == actual}
        for i in getattr(request, "axentra_sidebar_menu", [])
    ]


def _render(request, nombre, contexto):
    contexto = {**contexto, "show_module_sidebar": True, "sidebar_items": _menu(request)}
    destino = request.headers.get("HX-Target", "")
    if request.headers.get("HX-Request") == "true":
        if destino == "workbench":
            return render(request, f"permisos_personal/workbench/{nombre}.html", contexto)
        if destino == "page-content":
            return render(request, f"permisos_personal/content/{nombre}.html", contexto)
    return render(request, f"permisos_personal/pages/{nombre}.html", contexto)


def _errores(request, error):
    for mensaje in getattr(error, "messages", [str(error)]):
        messages.error(request, mensaje)


def _volver(request, defecto):
    destino = request.POST.get("volver", "")
    if destino and url_has_allowed_host_and_scheme(destino, allowed_hosts={request.get_host()}) and destino.startswith("/app/permisos-personal/"):
        return redirect(destino)
    return redirect(defecto)


def _entero(valor, defecto, minimo, maximo):
    try:
        return min(max(int(valor), minimo), maximo)
    except (TypeError, ValueError):
        return defecto


@login_required
@proteger_vista(APP_SLUG, "has_access_module")
def inicio_view(request):
    for llave, destino in (
        ("can_request_own", "mis_solicitudes"), ("can_view_calendar", "calendario"), ("can_view_all_requests", "solicitudes"),
    ):
        if permitido(request, llave):
            return redirect(f"permisos_personal:{destino}")
    raise PermissionDenied


# ---- Mis permisos -------------------------------------------------------------------------------------------------

@login_required
@proteger_vista(APP_SLUG, "can_request_own")
def mis_solicitudes_view(request):
    empleado = sel.empleado_de(request)
    anio = _entero(request.GET.get("anio"), timezone.localdate().year, 2000, 2100)
    contexto = {"empleado": empleado, "anio": anio}
    if empleado:
        contexto.update(
            saldos=services.saldos(empleado, anio),
            solicitudes=list(empleado.solicitudes.filter(anio=anio).order_by("-fecha_inicio")),
            anios=sorted({timezone.localdate().year - 1, timezone.localdate().year, timezone.localdate().year + 1, anio}),
        )
    return _render(request, "mis_solicitudes", contexto)


@login_required
@proteger_vista(APP_SLUG, "can_request_own")
def solicitud_crear_view(request):
    empleado = sel.empleado_de(request)
    if empleado is None:
        return _render(request, "solicitud_form", {"empleado": None, "form": None})
    form = SolicitudForm(request.POST or None, empleado=empleado)
    if request.method == "POST" and form.is_valid():
        datos = form.cleaned_data
        try:
            solicitud, avisos = services.crear_solicitud(
                empleado, usuario=request.user, tipo=datos["tipo"], fecha_inicio=datos["fecha_inicio"],
                fecha_fin=datos["fecha_fin"], comentarios=datos["comentarios"],
            )
        except ValidationError as error:
            form.add_error(None, error)
        else:
            messages.success(request, f"Solicitud registrada: {solicitud.get_tipo_display()} del {solicitud.fecha_inicio:%d/%m/%Y} al {solicitud.fecha_fin:%d/%m/%Y} ({solicitud.dias} día(s)).")
            for aviso in avisos:
                messages.warning(request, aviso)
            return redirect("permisos_personal:mis_solicitudes")
    anio = timezone.localdate().year
    return _render(request, "solicitud_form", {"empleado": empleado, "form": form, "saldos": services.saldos(empleado, anio), "anio": anio})


@login_required
@require_POST
@proteger_vista(APP_SLUG, "has_access_module")
def solicitud_cancelar_view(request, pk):
    solicitud = get_object_or_404(Solicitud.objects.select_related("empleado"), pk=pk)
    propia = solicitud.empleado.usuario_id == request.user.pk and permitido(request, "can_request_own")
    if not propia and not permitido(request, "can_validate_requests"):
        raise PermissionDenied
    try:
        services.cancelar_solicitud(solicitud, usuario=request.user, motivo=request.POST.get("motivo", ""), es_control=not propia)
    except ValidationError as error:
        _errores(request, error)
    else:
        messages.success(request, "Solicitud cancelada: el saldo se recuperó.")
    return _volver(request, "permisos_personal:mis_solicitudes")


# ---- Calendario -----------------------------------------------------------------------------------------------------

@login_required
@proteger_vista(APP_SLUG, "can_view_calendar")
def calendario_view(request):
    hoy = timezone.localdate()
    anio, mes = _entero(request.GET.get("anio"), hoy.year, 2000, 2100), _entero(request.GET.get("mes"), hoy.month, 1, 12)
    sedes = sedes_del_core()
    sede = request.GET.get("sede", "")
    sede = sede if sede in {str(pk) for pk, _ in sedes} else ""
    anterior = (datetime.date(anio, mes, 1) - datetime.timedelta(days=1))
    siguiente = datetime.date(anio, mes, pycal.monthrange(anio, mes)[1]) + datetime.timedelta(days=1)
    semanas = services.calendario_mes(anio, mes, sede or None)
    return _render(request, "calendario", {
        "semanas": semanas, "anio": anio, "mes": mes, "nombre_mes": MESES[mes - 1], "sedes": [(str(pk), n) for pk, n in sedes], "sede": sede,
        "anterior": {"anio": anterior.year, "mes": anterior.month}, "siguiente": {"anio": siguiente.year, "mes": siguiente.month},
        "hoy": hoy, "dias_semana": ("Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"),
        "con_alertas": sum(1 for s in semanas for dia in s if dia["bajo"]),
    })


# ---- Solicitudes (control) ------------------------------------------------------------------------------------------

ESTADOS = (("pendientes", "Por validar"), ("validadas", "Validadas"), ("canceladas", "Canceladas"), ("todas", "Todas"))


def _solicitudes_filtradas(request):
    """Filtros de la lista de solicitudes (los mismos para la pantalla y para el archivo de Excel)."""
    anio = _entero(request.GET.get("anio"), timezone.localdate().year, 2000, 2100)
    estado = request.GET.get("estado", "pendientes")
    estado = estado if estado in dict(ESTADOS) else "pendientes"
    base = sel.solicitudes_todas().filter(anio=anio)
    tipo, sede, texto = request.GET.get("tipo", ""), request.GET.get("sede", ""), request.GET.get("q", "").strip()[:80]
    if tipo in Solicitud.TipoSolicitud.values:
        base = base.filter(tipo=tipo)
    sedes = [(str(pk), n) for pk, n in sedes_del_core()]
    if sede in {pk for pk, _ in sedes}:
        base = base.filter(sede_uuid=sede)
    else:
        sede = ""
    for termino in texto.split()[:4]:
        base = base.filter(empleado__usuario__first_name__icontains=termino) | base.filter(empleado__usuario__last_name__icontains=termino)
    filtros = {
        "pendientes": {"estatus": "activa", "validado": False}, "validadas": {"estatus": "activa", "validado": True},
        "canceladas": {"estatus": "cancelada"}, "todas": {},
    }
    return {"anio": anio, "estado": estado, "tipo": tipo, "sede": sede, "texto": texto, "sedes": sedes, "base": base, "filas": base.filter(**filtros[estado]).order_by("fecha_inicio")}


@login_required
@proteger_vista(APP_SLUG, "can_view_all_requests")
def solicitudes_view(request):
    f = _solicitudes_filtradas(request)
    base, estado = f["base"], f["estado"]
    conteos = {
        "pendientes": base.filter(estatus="activa", validado=False).count(), "validadas": base.filter(estatus="activa", validado=True).count(),
        "canceladas": base.filter(estatus="cancelada").count(), "todas": base.count(),
    }
    filas = list(f["filas"])
    parametros = request.GET.copy()
    parametros.pop("pagina", None)
    return _render(request, "solicitudes", {
        "pagina": sel.pagina(filas, request.GET.get("pagina")), "estado": estado, "anio": f["anio"], "tipo": f["tipo"], "sede": f["sede"], "texto": f["texto"],
        "estados": [{"clave": c, "nombre": n, "total": conteos[c], "activa": c == estado} for c, n in ESTADOS], "sedes": f["sedes"],
        "tipos": Solicitud.TipoSolicitud.choices, "total": len(filas), "puede_validar": permitido(request, "can_validate_requests"),
        "query": parametros.urlencode(), "volver": request.get_full_path(),
    })


XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _descarga(contenido, nombre):
    respuesta = HttpResponse(contenido, content_type=XLSX)
    respuesta["Content-Disposition"] = f'attachment; filename="{nombre}"'
    return respuesta


@login_required
@proteger_vista(APP_SLUG, "can_view_all_requests")
def solicitudes_exportar_view(request):
    f = _solicitudes_filtradas(request)
    return _descarga(exportes.solicitudes_xlsx(list(f["filas"].select_related("validado_por"))), f"solicitudes-{f['anio']}-{f['estado']}.xlsx")


@login_required
@proteger_vista(APP_SLUG, "can_view_calendar")
def calendario_exportar_view(request):
    hoy = timezone.localdate()
    anio, mes = _entero(request.GET.get("anio"), hoy.year, 2000, 2100), _entero(request.GET.get("mes"), hoy.month, 1, 12)
    sede = request.GET.get("sede", "")
    sede = sede if sede in {str(pk) for pk, _ in sedes_del_core()} else ""
    return _descarga(exportes.ausencias_xlsx(services.calendario_mes(anio, mes, sede or None), mes), f"ausencias-{anio}-{mes:02d}.xlsx")


@login_required
@require_POST
@proteger_vista(APP_SLUG, "can_validate_requests")
def solicitud_validar_view(request, pk):
    solicitud = get_object_or_404(Solicitud, pk=pk)
    try:
        services.validar_solicitud(solicitud, usuario=request.user, validado=request.POST.get("validado") == "1")
    except ValidationError as error:
        _errores(request, error)
    return _volver(request, "permisos_personal:solicitudes")


# ---- Empleados ------------------------------------------------------------------------------------------------------

@login_required
@proteger_vista(APP_SLUG, "can_manage_employees")
def empleados_view(request):
    anio = timezone.localdate().year
    empleados = list(Empleado.objects.select_related("usuario").order_by("usuario__first_name", "usuario__last_name"))
    for e in empleados:
        e.antiguedad = cal.anios_de_antiguedad(e.fecha_ingreso, timezone.localdate())
        e.vac_p1, e.vac_p2 = services.dias_asignados(e, services.VACACIONES, anio, 1), services.dias_asignados(e, services.VACACIONES, anio, 2)
    return _render(request, "empleados", {"empleados": empleados, "anio": anio, "total": len(empleados)})


def _guardar_empleado(request, form, empleado):
    datos = form.cleaned_data
    sede_uuid = datos["sede"] or None
    return services.guardar_empleado(
        usuario_actor=request.user, empleado=empleado, usuario=datos["usuario"], tipo=datos["tipo"], fecha_ingreso=datos["fecha_ingreso"],
        sede_uuid=sede_uuid, sede_nombre=form._sedes.get(datos["sede"], ""), activo=datos["activo"],
    )


@login_required
@proteger_vista(APP_SLUG, "can_manage_employees")
def empleado_form_view(request, pk=None):
    empleado = get_object_or_404(Empleado.objects.select_related("usuario"), pk=pk) if pk else None
    form = EmpleadoForm(request.POST or None, empleado=empleado)
    if request.method == "POST" and form.is_valid():
        try:
            guardado = _guardar_empleado(request, form, empleado)
        except ValidationError as error:
            form.add_error(None, error)
        else:
            messages.success(request, f"{guardado.nombre} guardado.")
            return redirect("permisos_personal:empleado_detalle", pk=guardado.pk)
    return _render(request, "empleado_form", {"form": form, "empleado": empleado})


@login_required
@proteger_vista(APP_SLUG, "can_manage_employees")
def empleado_detalle_view(request, pk):
    empleado = get_object_or_404(Empleado.objects.select_related("usuario"), pk=pk)
    anio = _entero(request.GET.get("anio"), timezone.localdate().year, 2000, 2100)
    if request.method == "POST":
        accion = request.POST.get("accion")
        form = AjusteForm(request.POST)
        if form.is_valid():
            datos = form.cleaned_data
            try:
                if accion == "quitar":
                    services.quitar_ajuste(empleado, usuario=request.user, anio=datos["anio"], periodo=datos["periodo"])
                    messages.success(request, "Ajuste quitado: vuelve a aplicar la tabla por antigüedad.")
                else:
                    services.ajustar_dias(empleado, usuario=request.user, anio=datos["anio"], periodo=datos["periodo"], dias=datos["dias"])
                    messages.success(request, "Días de vacaciones ajustados.")
            except ValidationError as error:
                _errores(request, error)
        else:
            messages.error(request, "Revise el año, el periodo y los días.")
        return redirect(f"{reverse('permisos_personal:empleado_detalle', args=[empleado.pk])}?anio={anio}")
    filas = services.saldos(empleado, anio)
    for f in filas:
        if f["tipo"] == services.VACACIONES:
            f["tabla"] = services.dias_de_tabla(empleado, anio, f["periodo"])
            f["ajustado"] = f["tabla"] != f["asignados"]
    return _render(request, "empleado_detalle", {
        "empleado": empleado, "anio": anio, "saldos": filas, "antiguedad": cal.anios_de_antiguedad(empleado.fecha_ingreso, timezone.localdate()),
        "solicitudes": list(empleado.solicitudes.filter(anio=anio).order_by("-fecha_inicio")), "movimientos": list(empleado.movimientos.order_by("-created_at")[:15]),
        "ajuste_form": AjusteForm(initial={"anio": anio, "periodo": 1, "dias": 0}),
    })


# ---- Configuración --------------------------------------------------------------------------------------------------

@login_required
@proteger_vista(APP_SLUG, "can_manage_config")
def configuracion_view(request):
    configuracion = Configuracion.obtener()
    sedes = sedes_del_core()
    if request.method == "POST":
        accion = request.POST.get("accion")
        if accion == "economicos":
            form = ConfiguracionForm(request.POST, instance=configuracion)
            if form.is_valid():
                form.save()
                messages.success(request, "Días económicos actualizados para todo el personal sindicalizado.")
            else:
                messages.error(request, "Revise los días económicos.")
        elif accion == "rango":
            form = RangoForm(request.POST)
            if form.is_valid():
                datos = form.cleaned_data
                _, creado = RangoAntiguedad.objects.update_or_create(
                    tipo=datos["tipo"], desde_anios=datos["desde_anios"], defaults={"dias_p1": datos["dias_p1"], "dias_p2": datos["dias_p2"]},
                )
                messages.success(request, "Fila agregada a la tabla." if creado else "Fila actualizada.")
            else:
                messages.error(request, "Revise la fila de la tabla de antigüedad.")
        elif accion == "rango_eliminar":
            RangoAntiguedad.objects.filter(pk=request.POST.get("id")).delete()
            messages.success(request, "Fila eliminada.")
        elif accion == "umbral":
            nombres = {str(pk): n for pk, n in sedes}
            sede = request.POST.get("sede", "")
            minimo = _entero(request.POST.get("minimo"), -1, 0, 500)
            if sede in nombres and minimo >= 0:
                UmbralSede.objects.update_or_create(sede_uuid=sede, defaults={"sede_nombre": nombres[sede], "minimo": minimo})
                messages.success(request, f"Mínimo de {nombres[sede]}: {minimo}.")
            else:
                messages.error(request, "Revise la sede y el mínimo.")
        return redirect("permisos_personal:configuracion")
    minimos = {str(u.sede_uuid): u.minimo for u in UmbralSede.objects.all()}
    personal = {}
    for e in Empleado.objects.filter(is_active=True):
        personal[str(e.sede_uuid)] = personal.get(str(e.sede_uuid), 0) + 1
    return _render(request, "configuracion", {
        "economicos_form": ConfiguracionForm(instance=configuracion), "rango_form": RangoForm(),
        "rangos": [{"clave": t, "nombre": n, "filas": list(RangoAntiguedad.objects.filter(tipo=t))} for t, n in Tipo.choices],
        "sedes": [{"uuid": str(pk), "nombre": n, "minimo": minimos.get(str(pk), 1), "personal": personal.get(str(pk), 0)} for pk, n in sedes],
    })
