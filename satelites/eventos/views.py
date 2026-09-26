import calendar as pycal
import datetime

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from . import selectors as sel
from . import services
from .forms import AsignarForm, EventoForm, TextoForm, TramiteForm, ValeForm
from .integracion import proteger_vista, url_de_vale
from .models import Asignacion, Evento, TramiteLinea, ValeSalida
from .selectors import APP_SLUG, permitido

MESES = ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre")
DIAS_SEMANA = ("Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom")


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
            return render(request, f"eventos/workbench/{nombre}.html", contexto)
        if destino == "page-content":
            return render(request, f"eventos/content/{nombre}.html", contexto)
    return render(request, f"eventos/pages/{nombre}.html", contexto)


def _errores(request, error):
    for mensaje in getattr(error, "messages", [str(error)]):
        messages.error(request, mensaje)


def _entero(valor, defecto, minimo, maximo):
    try:
        return min(max(int(valor), minimo), maximo)
    except (TypeError, ValueError):
        return defecto


@login_required
@proteger_vista(APP_SLUG, "has_access_module")
def inicio_view(request):
    for llave, destino in (("can_view_own", "mis_eventos"), ("can_view_calendar", "calendario"), ("can_view_all_events", "eventos")):
        if permitido(request, llave):
            return redirect(f"eventos:{destino}")
    raise PermissionDenied


# ---- Mis eventos --------------------------------------------------------------------------------------------------

def _con_empalme(asignaciones):
    for a in asignaciones:
        a.empalmada = bool(services.empalmes(a.tecnico, a.desde, a.hasta, excluir=a.evento)) if a.evento.abierto else False
    return asignaciones


@login_required
@proteger_vista(APP_SLUG, "can_view_own")
def mis_eventos_view(request):
    proximas = _con_empalme(list(sel.proximas_de(request.user)))
    return _render(request, "mis_eventos", {
        "proximas": proximas, "proxima": proximas[0] if proximas else None,
        "recientes": sel.recientes_de(request.user), "ahora": timezone.now(),
    })


# ---- Calendario ---------------------------------------------------------------------------------------------------

@login_required
@proteger_vista(APP_SLUG, "can_view_calendar")
def calendario_view(request):
    hoy = timezone.localdate()
    anio, mes = _entero(request.GET.get("anio"), hoy.year, 2000, 2100), _entero(request.GET.get("mes"), hoy.month, 1, 12)
    tecnico = request.GET.get("tecnico", "")
    tecnicos = sel.tecnicos_con_eventos()
    tecnico = tecnico if tecnico in {str(pk) for pk, _ in tecnicos} else ""
    anterior = datetime.date(anio, mes, 1) - datetime.timedelta(days=1)
    siguiente = datetime.date(anio, mes, pycal.monthrange(anio, mes)[1]) + datetime.timedelta(days=1)
    return _render(request, "calendario", {
        "anio": anio, "mes": mes, "nombre_mes": MESES[mes - 1].capitalize(), "dias_semana": DIAS_SEMANA, "hoy": hoy,
        "semanas": services.calendario_mes(anio, mes, tecnico or None), "tecnicos": tecnicos, "tecnico": tecnico,
        "anterior": {"anio": anterior.year, "mes": anterior.month}, "siguiente": {"anio": siguiente.year, "mes": siguiente.month},
    })


# ---- Lista --------------------------------------------------------------------------------------------------------

@login_required
@proteger_vista(APP_SLUG, "can_view_all_events")
def eventos_view(request):
    estado = request.GET.get("estado", "abiertos")
    texto = request.GET.get("q", "").strip()
    tecnico = request.GET.get("tecnico", "")
    base = sel.eventos_todos()
    if texto:
        from django.db.models import Q
        base = base.filter(Q(nombre__icontains=texto) | Q(lugar__icontains=texto) | Q(ticket__icontains=texto))
    if tecnico:
        base = base.filter(asignaciones__tecnico_id=tecnico).distinct()
    grupos = (
        ("abiertos", "Próximos y en curso", base.filter(estatus__in=sel.ABIERTOS)),
        ("concluidos", "Concluidos", base.filter(estatus=Evento.Estatus.CONCLUIDO)),
        ("cancelados", "Cancelados", base.filter(estatus=Evento.Estatus.CANCELADO)),
        ("todos", "Todos", base),
    )
    estado = estado if estado in {g[0] for g in grupos} else "abiertos"
    estados = [{"clave": c, "nombre": n, "total": q.count(), "activa": c == estado} for c, n, q in grupos]
    elegido = next(q for c, _, q in grupos if c == estado)
    orden = "-inicio" if estado in ("concluidos", "cancelados", "todos") else "inicio"
    consulta = request.GET.copy()
    consulta.pop("pagina", None)
    return _render(request, "eventos", {
        "pagina": sel.pagina(elegido.order_by(orden), request.GET.get("pagina")), "estados": estados, "estado": estado,
        "texto": texto, "tecnico": tecnico, "tecnicos": sel.tecnicos_con_eventos(), "query": consulta.urlencode(),
        "ahora": timezone.now(),
    })


# ---- Alta y edición -----------------------------------------------------------------------------------------------

@login_required
@proteger_vista(APP_SLUG, "can_manage_events")
@require_http_methods(["GET", "POST"])
def evento_form_view(request, pk=None):
    evento = get_object_or_404(Evento, pk=pk) if pk else None
    if evento and not evento.abierto:
        messages.error(request, "Un evento %s ya no se puede editar." % evento.get_estatus_display().lower())
        return redirect("eventos:evento_detalle", pk=evento.pk)
    form = EventoForm(request.POST or None, evento=evento)
    if request.method == "POST" and form.is_valid():
        try:
            if evento:
                services.editar_evento(evento, usuario=request.user, **form.cleaned_data)
                messages.success(request, "Evento actualizado.")
            else:
                evento = services.crear_evento(usuario=request.user, **form.cleaned_data)
                messages.success(request, "Evento creado. Ahora asigne técnicos y vincule los vales de salida.")
            return redirect("eventos:evento_detalle", pk=evento.pk)
        except ValidationError as error:
            _errores(request, error)
    return _render(request, "evento_form", {"form": form, "evento": evento})


# ---- Detalle y acciones -------------------------------------------------------------------------------------------

def _accion(request, evento, accion):
    """Ejecuta una acción del detalle. Devuelve el formulario con errores si no es válido, o None."""
    usuario = request.user
    if accion == "nota":
        if not permitido(request, "can_add_notes"):
            raise PermissionDenied
        form = TextoForm(request.POST)
        if form.is_valid():
            services.agregar_nota(evento, usuario=usuario, texto=form.cleaned_data["texto"])
            messages.success(request, "Nota agregada.")
            return None
        return form
    if not permitido(request, "can_manage_events"):
        raise PermissionDenied
    if accion == "asignar":
        form = AsignarForm(request.POST)
        if form.is_valid():
            _, avisos = services.asignar_tecnico(evento, usuario=usuario, **form.cleaned_data)
            messages.success(request, "Técnico asignado.")
            for aviso in avisos:
                messages.warning(request, aviso)
            return None
        return form
    if accion == "quitar_tecnico":
        services.quitar_tecnico(get_object_or_404(Asignacion, pk=request.POST.get("id"), evento=evento), usuario=usuario)
        messages.success(request, "Tramo quitado.")
    elif accion == "vale":
        form = ValeForm(request.POST)
        if form.is_valid():
            services.vincular_vale(evento, usuario=usuario, **form.cleaned_data)
            messages.success(request, "Vale vinculado.")
            return None
        return form
    elif accion == "quitar_vale":
        services.desvincular_vale(get_object_or_404(ValeSalida, pk=request.POST.get("id"), evento=evento), usuario=usuario)
        messages.success(request, "Vale desvinculado.")
    elif accion == "tramite":
        form = TramiteForm(request.POST)
        if form.is_valid():
            services.agregar_tramite(evento, usuario=usuario, **form.cleaned_data)
            messages.success(request, "Trámite agregado.")
            return None
        return form
    elif accion == "tramite_estado":
        services.cambiar_estado_tramite(get_object_or_404(TramiteLinea, pk=request.POST.get("id"), evento=evento), usuario=usuario, estado=request.POST.get("estado", ""))
        messages.success(request, "Trámite actualizado.")
    elif accion == "quitar_tramite":
        services.quitar_tramite(get_object_or_404(TramiteLinea, pk=request.POST.get("id"), evento=evento), usuario=usuario)
        messages.success(request, "Trámite quitado.")
    elif accion == "iniciar":
        services.iniciar_evento(evento, usuario=usuario)
        messages.success(request, "Evento en curso.")
    elif accion == "concluir":
        services.concluir_evento(evento, usuario=usuario, notas=request.POST.get("notas", ""))
        messages.success(request, "Evento concluido.")
    elif accion == "cancelar":
        services.cancelar_evento(evento, usuario=usuario, motivo=request.POST.get("motivo", ""))
        messages.success(request, "Evento cancelado.")
    else:
        raise PermissionDenied
    return None


@login_required
@proteger_vista(APP_SLUG, "can_view_all_events")
@require_http_methods(["GET", "POST"])
def evento_detalle_view(request, pk):
    evento = get_object_or_404(Evento.objects.prefetch_related("asignaciones", "vales", "tramites"), pk=pk)
    formularios = {}
    if request.method == "POST":
        accion = request.POST.get("accion", "")
        try:
            invalido = _accion(request, evento, accion)
        except ValidationError as error:
            _errores(request, error)
            invalido = None
        else:
            if invalido is None:
                return redirect("eventos:evento_detalle", pk=evento.pk)
        if invalido is not None:
            formularios[accion] = invalido
        evento = get_object_or_404(Evento.objects.prefetch_related("asignaciones", "vales", "tramites"), pk=pk)
    asignaciones = list(evento.asignaciones.select_related("tecnico"))
    for a in asignaciones:
        a.avisos = services.empalmes(a.tecnico, a.desde, a.hasta, excluir=evento) if evento.abierto else []
    vales = list(evento.vales.all())
    for v in vales:
        v.url = url_de_vale(v.referencia)
    return _render(request, "evento_detalle", {
        "evento": evento, "asignaciones": asignaciones, "vales": vales, "tramites": list(evento.tramites.all()),
        "bitacora": list(evento.bitacora.all()[:50]), "estados_tramite": TramiteLinea.Estado.choices,
        "puede_gestionar": permitido(request, "can_manage_events"), "puede_notas": permitido(request, "can_add_notes"),
        "form_asignar": formularios.get("asignar") or AsignarForm(), "form_vale": formularios.get("vale") or ValeForm(),
        "form_tramite": formularios.get("tramite") or TramiteForm(), "form_nota": formularios.get("nota") or TextoForm(),
        "asignar_desde": evento.inicio, "asignar_hasta": evento.fin,
    })
