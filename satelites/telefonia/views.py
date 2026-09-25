import uuid
from collections import Counter

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from . import selectors as sel
from . import services
from .forms import (
    AtenderForm, ComentarioForm, EvidenciaForm, LineaForm, MotivoForm, ReporteEdicionForm, ReporteForm,
)
from .integracion import nombre_de_usuario, proteger_vista, telefono_de_usuario, usuarios_con_acceso
from .models import Evidencia, Linea, Reporte
from .selectors import APP_SLUG, permitido
from .storage import almacen


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
            return render(request, f"telefonia/workbench/{nombre}.html", contexto)
        if destino == "page-content":
            return render(request, f"telefonia/content/{nombre}.html", contexto)
    return render(request, f"telefonia/pages/{nombre}.html", contexto)


def _query(request, *, quitar=(), **poner):
    parametros = request.GET.copy()
    for clave in ("pagina", *quitar):
        parametros.pop(clave, None)
    for clave, valor in poner.items():
        parametros[clave] = valor
    return parametros.urlencode()


def _errores(request, error):
    for mensaje in getattr(error, "messages", [str(error)]):
        messages.error(request, mensaje)


@login_required
@proteger_vista(APP_SLUG, "has_access_module")
def inicio_view(request):
    for llave, destino in (("can_view_reports", "reportes"), ("can_view_own_reports", "mis_pendientes")):
        if permitido(request, llave):
            return redirect(f"telefonia:{destino}")
    raise PermissionDenied


# ---- Reportes -------------------------------------------------------------------------------------------------

@login_required
@proteger_vista(APP_SLUG, "can_view_reports")
def reportes_view(request):
    texto = request.GET.get("q", "").strip()[:100]
    base = sel.buscar_reportes(sel.reportes_visibles(request), texto)
    tab = sel.tab_valida(request.GET.get("tab"))
    conteos = {clave: (base.filter(estatus__in=e).count() if e else base.count()) for clave, _, e in sel.TABS}
    filas = list(sel.aplicar_tab(base, tab))
    semaforo = request.GET.get("semaforo", "")
    tiles = []
    if tab == "pendientes":
        resumen = Counter(r.color for r in filas)
        tiles = [
            {"clave": c, "nombre": n, "total": resumen.get(c, 0), "activo": semaforo == c,
             "query": _query(request, quitar=("semaforo",)) if semaforo == c else _query(request, semaforo=c)}
            for c, n in (("rojo", "Rojo"), ("ambar", "Ámbar"), ("verde", "Verde"))
        ]
        if semaforo in ("verde", "ambar", "rojo"):
            filas = [r for r in filas if r.color == semaforo]
            filas.sort(key=lambda r: -r.dias_abierto)
        else:
            filas.sort(key=lambda r: -r.dias_abierto)
    ambar, rojo = sel.semaforo_umbrales()
    return _render(request, "reportes", {
        "pagina": sel.pagina(filas, request.GET.get("pagina")), "tab": tab, "texto": texto, "total": len(filas),
        "tabs": [{"clave": c, "nombre": n, "total": conteos[c], "activa": c == tab, "query": _query(request, quitar=("semaforo",), tab=c)} for c, n, _ in sel.TABS],
        "tiles": tiles, "umbral_ambar": ambar, "umbral_rojo": rojo, "query_sin_pagina": _query(request),
        "puede_crear": permitido(request, "can_create_report"),
    })


@login_required
@proteger_vista(APP_SLUG, "can_view_own_reports")
def mis_pendientes_view(request):
    pendientes = list(sel.reportes_propios(request).filter(estatus=Reporte.Estatus.PENDIENTE).order_by("levantado"))
    recientes = list(sel.reportes_propios(request).exclude(estatus=Reporte.Estatus.PENDIENTE).order_by("-updated_at")[:5])
    return _render(request, "mis_pendientes", {"pendientes": pendientes, "recientes": recientes})


def _datos_de_lineas(request, lineas):
    """Lo que necesita el mapa y el buscador: coordenadas y el color del reporte abierto más viejo de cada línea."""
    abiertos = {}
    for linea_id, levantado in Reporte.objects.filter(estatus=Reporte.Estatus.PENDIENTE, is_deleted=False).values_list("linea_id", "levantado"):
        actual = abiertos.setdefault(linea_id, {"n": 0, "dias": 0})
        actual["n"] += 1
        actual["dias"] = max(actual["dias"], (timezone.localdate() - levantado).days)
    datos = []
    for linea in lineas:
        estado = abiertos.get(linea.pk)
        datos.append({
            "id": str(linea.pk), "identificador": linea.identificador, "sitio": linea.sitio, "tipo": linea.get_tipo_display(),
            "direccion": linea.direccion, "velocidad": linea.velocidad,
            "lat": float(linea.latitud) if linea.latitud is not None else None,
            "lng": float(linea.longitud) if linea.longitud is not None else None,
            "abiertos": estado["n"] if estado else 0, "estado": sel.color_semaforo(estado["dias"]) if estado else "ninguno",
        })
    return datos


@login_required
@proteger_vista(APP_SLUG, "can_create_report")
def reporte_crear_view(request):
    lineas = sel.lineas_visibles(request).filter(is_active=True)
    responsables = usuarios_con_acceso(APP_SLUG)
    inicial = {}
    previa = request.GET.get("linea", "")
    if previa:
        try:
            inicial["linea"] = lineas.filter(pk=uuid.UUID(previa)).first()
        except ValueError:
            pass
    form = ReporteForm(request.POST or None, lineas=lineas, responsables=responsables, initial=inicial)
    aviso = []
    if request.method == "POST" and form.is_valid():
        datos = form.cleaned_data
        try:
            reporte = services.crear_reporte(usuario=request.user, **datos)
        except ValidationError as error:
            form.add_error(None, error)
        else:
            otros = services.reportes_abiertos_de(reporte.linea).exclude(pk=reporte.pk).count()
            messages.success(request, f"Reporte {reporte.folio} registrado." + (f" Ojo: la línea tiene {otros} reporte(s) más abierto(s)." if otros else ""))
            return redirect("telefonia:reporte_detalle", pk=reporte.pk)
    return _render(request, "reporte_form", {
        "form": form, "lineas_data": _datos_de_lineas(request, lineas),
        "responsables_data": [{"id": str(u.pk), "nombre": nombre_de_usuario(u), "telefono": telefono_de_usuario(u)} for u in responsables],
        "linea_inicial": str(inicial["linea"].pk) if inicial.get("linea") else str(form["linea"].value() or ""),
        "aviso": aviso,
    })


def _reporte_visible(request, pk):
    reportes = sel.reportes_visibles(request)
    if not permitido(request, "can_view_reports"):
        if not permitido(request, "can_view_own_reports"):
            raise PermissionDenied
        reportes = reportes.filter(responsable=request.user)
    return get_object_or_404(reportes, pk=pk)


def _puede_actualizar(request, reporte):
    return permitido(request, "can_update_report") or (
        permitido(request, "can_update_own_report") and reporte.responsable_id == request.user.pk
    )


@login_required
@proteger_vista(APP_SLUG, "has_access_module")
def reporte_detalle_view(request, pk):
    reporte = _reporte_visible(request, pk)
    puede = _puede_actualizar(request, reporte) and reporte.estatus != Reporte.Estatus.CANCELADO
    otros = Reporte.objects.filter(linea=reporte.linea, is_deleted=False).exclude(pk=reporte.pk).order_by("-levantado")[:8]
    return _render(request, "reporte_detalle", {
        "reporte": reporte, "movimientos": list(reporte.movimientos.all()), "evidencias": list(reporte.evidencias.filter(is_deleted=False)),
        "otros_reportes": otros, "linea_data": _datos_de_lineas(request, [reporte.linea]),
        "puede_actualizar": puede, "puede_gestionar": permitido(request, "can_update_report") and reporte.estatus != Reporte.Estatus.CANCELADO,
        "puede_cancelar": permitido(request, "can_cancel_report"),
        "comentario_form": ComentarioForm(), "evidencia_form": EvidenciaForm(), "atender_form": AtenderForm(), "motivo_form": MotivoForm(),
        "responsables": usuarios_con_acceso(APP_SLUG) if permitido(request, "can_update_report") else [],
        "es_movil_propio": reporte.responsable_id == request.user.pk,
    })


def _accion(request, pk, hacer, exito, *, gestion=False, cancelacion=False):
    reporte = _reporte_visible(request, pk)
    if cancelacion:
        if not permitido(request, "can_cancel_report"):
            raise PermissionDenied
    elif gestion:
        if not permitido(request, "can_update_report"):
            raise PermissionDenied
    elif not _puede_actualizar(request, reporte):
        raise PermissionDenied
    try:
        hacer(reporte)
    except ValidationError as error:
        _errores(request, error)
    else:
        messages.success(request, exito)
    return redirect("telefonia:reporte_detalle", pk=reporte.pk)


@login_required
@require_POST
@proteger_vista(APP_SLUG, "has_access_module")
def reporte_comentar_view(request, pk):
    form = ComentarioForm(request.POST)
    return _accion(request, pk, lambda r: services.comentar(r, usuario=request.user, texto=form.data.get("texto", "")), "Comentario agregado.")


@login_required
@require_POST
@proteger_vista(APP_SLUG, "has_access_module")
def reporte_evidencia_view(request, pk):
    form = EvidenciaForm(request.POST, request.FILES)
    if not form.is_valid():
        messages.error(request, "Elija la foto o captura que va a subir.")
        return redirect("telefonia:reporte_detalle", pk=pk)
    datos = form.cleaned_data
    return _accion(request, pk, lambda r: services.subir_evidencia(r, usuario=request.user, archivo=datos["archivo"], tipo=datos["tipo"]), "Evidencia agregada.")


@login_required
@require_POST
@proteger_vista(APP_SLUG, "has_access_module")
def reporte_atender_view(request, pk):
    form = AtenderForm(request.POST)
    datos = form.cleaned_data if form.is_valid() else {}
    return _accion(
        request, pk, lambda r: services.marcar_atendido(r, usuario=request.user, fecha=datos.get("fecha"), comentario=datos.get("comentario", "")),
        "Reporte marcado como atendido.",
    )


@login_required
@require_POST
@proteger_vista(APP_SLUG, "has_access_module")
def reporte_cancelar_view(request, pk):
    motivo = request.POST.get("motivo", "")
    return _accion(request, pk, lambda r: services.cancelar(r, usuario=request.user, motivo=motivo), "Reporte cancelado.", cancelacion=True)


@login_required
@require_POST
@proteger_vista(APP_SLUG, "has_access_module")
def reporte_reabrir_view(request, pk):
    motivo = request.POST.get("motivo", "")
    return _accion(request, pk, lambda r: services.reabrir(r, usuario=request.user, motivo=motivo), "Reporte reabierto.", cancelacion=True)


@login_required
@require_POST
@proteger_vista(APP_SLUG, "has_access_module")
def reporte_asignar_view(request, pk):
    responsable = usuarios_con_acceso(APP_SLUG).filter(pk=request.POST.get("responsable") or None).first()
    return _accion(request, pk, lambda r: services.asignar_responsable(r, usuario=request.user, responsable=responsable), "Responsable actualizado.", gestion=True)


@login_required
@proteger_vista(APP_SLUG, "can_update_report")
def reporte_editar_view(request, pk):
    reporte = _reporte_visible(request, pk)
    form = ReporteEdicionForm(request.POST or None, reporte=reporte)
    if request.method == "POST" and form.is_valid():
        datos = dict(form.cleaned_data)
        motivo = datos.pop("motivo", "")
        try:
            services.editar_reporte(reporte, usuario=request.user, cambios=datos, motivo=motivo)
        except ValidationError as error:
            form.add_error(None, error)
        else:
            messages.success(request, "Reporte corregido.")
            return redirect("telefonia:reporte_detalle", pk=reporte.pk)
    return _render(request, "reporte_editar", {"form": form, "reporte": reporte})


@login_required
@proteger_vista(APP_SLUG, "has_access_module")
def evidencia_descargar_view(request, pk, evidencia_pk):
    reporte = _reporte_visible(request, pk)
    evidencia = get_object_or_404(Evidencia, pk=evidencia_pk, reporte=reporte, is_deleted=False)
    try:
        archivo = almacen().open(evidencia.ruta, "rb")
    except FileNotFoundError as error:
        raise Http404("El archivo ya no está en el almacén.") from error
    respuesta = FileResponse(archivo, content_type=evidencia.content_type)
    respuesta["Content-Disposition"] = f'inline; filename="{evidencia.nombre_original}"'
    respuesta["X-Content-Type-Options"] = "nosniff"
    return respuesta


# ---- Líneas y mapa ------------------------------------------------------------------------------------------------

@login_required
@proteger_vista(APP_SLUG, "can_view_reports")
def lineas_view(request):
    texto = request.GET.get("q", "").strip()[:100]
    tipo = request.GET.get("tipo", "")
    lineas = sel.buscar_lineas(sel.lineas_visibles(request), texto)
    if tipo in Linea.Tipo.values:
        lineas = lineas.filter(tipo=tipo)
    else:
        tipo = ""
    filas = list(lineas)
    datos = {d["id"]: d for d in _datos_de_lineas(request, filas)}
    for linea in filas:
        linea.estado = datos[str(linea.pk)]["estado"]
        linea.abiertos = datos[str(linea.pk)]["abiertos"]
    return _render(request, "lineas", {
        "pagina": sel.pagina(filas, request.GET.get("pagina")), "texto": texto, "tipo": tipo, "tipos": Linea.Tipo.choices,
        "total": len(filas), "query_sin_pagina": _query(request), "puede_gestionar": permitido(request, "can_manage_lines"),
    })


@login_required
@proteger_vista(APP_SLUG, "can_manage_lines")
def linea_form_view(request, pk=None):
    linea = get_object_or_404(sel.lineas_visibles(request), pk=pk) if pk else None
    form = LineaForm(request.POST or None, instance=linea)
    if request.method == "POST" and form.is_valid():
        guardada = form.save()
        messages.success(request, f"Línea {guardada.identificador} guardada.")
        return redirect("telefonia:linea_detalle", pk=guardada.pk)
    return _render(request, "linea_form", {"form": form, "linea": linea})


@login_required
@proteger_vista(APP_SLUG, "can_view_reports")
def linea_detalle_view(request, pk):
    linea = get_object_or_404(sel.lineas_visibles(request), pk=pk)
    return _render(request, "linea_detalle", {
        "linea": linea, "linea_data": _datos_de_lineas(request, [linea]),
        "reportes": list(linea.reportes.filter(is_deleted=False).order_by("-levantado")),
        "puede_gestionar": permitido(request, "can_manage_lines"), "puede_crear": permitido(request, "can_create_report"),
    })


@login_required
@proteger_vista(APP_SLUG, "can_view_reports")
def mapa_view(request):
    lineas = list(sel.lineas_visibles(request).filter(is_active=True))
    datos = _datos_de_lineas(request, lineas)
    return _render(request, "mapa", {
        "lineas_data": datos, "con_mapa": sum(1 for d in datos if d["lat"] is not None), "sin_mapa": sum(1 for d in datos if d["lat"] is None),
    })
