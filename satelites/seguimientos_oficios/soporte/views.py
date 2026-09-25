from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render

from ..integracion import nombre_de_usuario, proteger_vista
from ..models import ClaseDocumento
from ..selectors import APP_SLUG, permitido
from ..views import _query, _render
from . import selectors as sel
from .forms import AltaForm, BajaForm, DiagnosticoForm, leer_equipos
from .services import CLASIFICACIONES, DISPOSICIONES, ETIQUETAS, RECOMENDACIONES, emitir_alta, emitir_baja, emitir_diagnostico

TABS = (
    ("todos", "Todos", None),
    ("diagnosticos", "Diagnósticos", ClaseDocumento.DIAGNOSTICO_TECNICO),
    ("bajas", "Bajas", ClaseDocumento.DICTAMEN_BAJA),
    ("altas", "Altas", ClaseDocumento.DICTAMEN_ALTA),
)


@login_required
@proteger_vista(APP_SLUG, "can_view_support")
def soporte_view(request):
    dictamenes = list(sel.dictamenes_visibles(request).order_by("-documento__fecha", "-created_at"))
    tab = request.GET.get("tab", "todos")
    if tab not in {c for c, _, _ in TABS}:
        tab = "todos"
    conteos = {c: sum(1 for d in dictamenes if clase is None or d.documento.clase == clase) for c, _, clase in TABS}
    clase = next(k for c, _, k in TABS if c == tab)
    filas = [d for d in dictamenes if clase is None or d.documento.clase == clase]
    pagina = Paginator(filas, 25).get_page(request.GET.get("pagina"))
    return _render(request, "soporte", {
        "pagina": pagina, "tab": tab, "total": len(filas), "area_actual": "soporte",
        "tabs": [{"clave": c, "nombre": n, "total": conteos[c], "activa": c == tab, "query": _query(request, tab=c)} for c, n, _ in TABS],
        "query_sin_pagina": _query(request, tab=tab),
        "puede_gestionar": permitido(request, "can_manage_support"),
    })


def _contexto_form(request, form, clase, titulo, descripcion, equipos=None, un_equipo=False, errores_equipos=()):
    catalogo = [
        {"id": str(b.pk), "texto": f"{b}", "equipo": b.nombre, "marca_modelo": b.marca_modelo, "serie": b.identificador,
         "folio_inventario": b.folio_inventario, "departamento": b.direccion.nombre}
        for b in sel.bienes_catalogo(request)
    ]
    return {
        "form": form, "titulo": titulo, "descripcion": descripcion, "clase": clase, "area_actual": "soporte",
        "catalogo": catalogo, "equipos": equipos or [{}], "un_equipo": un_equipo, "errores_equipos": errores_equipos,
        "sin_habilitar": not sel.direcciones_con_soporte(request, "can_manage_support").exists(),
        "recomendaciones": RECOMENDACIONES, "clasificaciones": CLASIFICACIONES, "disposiciones": DISPOSICIONES,
    }


def _equipos_para_reabrir(request):
    filas, _ = leer_equipos(request.POST, sel.bienes_catalogo(request))
    return [{**f, "bien": f["bien"].pk if f.get("bien") else ""} for f in filas] or [{}]


def _base_kwargs(request, datos):
    return {
        "usuario": request.user, "direccion": datos["direccion"], "ticket": datos["ticket"],
        "elaboro_nombre": nombre_de_usuario(request.user), "elaboro_cargo": datos["elaboro_cargo"],
    }


def _terminar(request, documento):
    messages.success(request, f"{documento.get_clase_display()} {documento.folio} emitido. Ya puedes imprimirlo para firmarlo.")
    return redirect("seguimientos_oficios:documento_detail", pk=documento.pk)


@login_required
@proteger_vista(APP_SLUG, "can_manage_support")
def crear_diagnostico_view(request):
    direcciones = sel.direcciones_con_soporte(request, "can_manage_support")
    titulo, ayuda = "Nuevo diagnóstico técnico", "Estado físico y funcionamiento de un bien, con su recomendación."
    if not direcciones.exists():
        return _render(request, "soporte_form", _contexto_form(request, None, "diagnostico", titulo, ayuda))
    form = DiagnosticoForm(request.POST or None, direcciones=direcciones)
    equipos, errores = [{}], []
    if request.method == "POST":
        equipos, errores = leer_equipos(request.POST, sel.bienes_catalogo(request))
        if form.is_valid() and not errores:
            datos = form.cleaned_data
            try:
                documento, _ = emitir_diagnostico(
                    **_base_kwargs(request, datos), solicitante=datos["solicitante"], equipo=(equipos or [{}])[0],
                    datos={
                        "fecha_recibido": datos["fecha_recibido"].isoformat(), "tipo_bien": datos["tipo_bien"],
                        "fallo": datos["fallo"], "causa": datos["causa"], "solucion": datos["solucion"],
                        "observaciones": datos["observaciones"], "recomendacion": datos["recomendacion"],
                        "solicito": datos["solicitante"],
                    },
                )
            except ValidationError as error:
                form.add_error(None, error)
            else:
                return _terminar(request, documento)
        equipos = _equipos_para_reabrir(request)
    return _render(request, "soporte_form", _contexto_form(request, form, "diagnostico", titulo, ayuda, equipos, True, errores))


@login_required
@proteger_vista(APP_SLUG, "can_manage_support")
def crear_baja_view(request):
    direcciones = sel.direcciones_con_soporte(request, "can_manage_support")
    titulo, ayuda = "Nuevo dictamen de baja", "Los bienes del catálogo que ampare pasan a estado Baja al emitirlo."
    if not direcciones.exists():
        return _render(request, "soporte_form", _contexto_form(request, None, "baja", titulo, ayuda))
    form = BajaForm(request.POST or None, direcciones=direcciones)
    equipos, errores = [{}], []
    if request.method == "POST":
        equipos, errores = leer_equipos(request.POST, sel.bienes_catalogo(request))
        if form.is_valid() and not errores:
            datos = form.cleaned_data
            try:
                documento, _ = emitir_baja(
                    **_base_kwargs(request, datos), contraparte=datos["contraparte"],
                    contraparte_dependencia_uuid=datos["contraparte_dependencia_uuid"], equipos=equipos,
                    autoriza_nombre=datos["autoriza_nombre"], autoriza_cargo=datos["autoriza_cargo"],
                    datos={
                        "diagnostico": datos["diagnostico"], "clasificacion": datos["clasificacion"],
                        "disposicion": datos["disposicion"], "solicito": datos["solicitante"],
                    },
                )
            except ValidationError as error:
                form.add_error(None, error)
            else:
                return _terminar(request, documento)
        equipos = _equipos_para_reabrir(request)
    return _render(request, "soporte_form", _contexto_form(request, form, "baja", titulo, ayuda, equipos, False, errores))


@login_required
@proteger_vista(APP_SLUG, "can_manage_support")
def crear_alta_view(request):
    direcciones = sel.direcciones_con_soporte(request, "can_manage_support")
    titulo, ayuda = "Nuevo dictamen de alta", "Solicitud para que el departamento tramite el alta del bien en Ingresos. No da de alta el bien en el catálogo."
    if not direcciones.exists():
        return _render(request, "soporte_form", _contexto_form(request, None, "alta", titulo, ayuda))
    form = AltaForm(request.POST or None, direcciones=direcciones)
    if request.method == "POST" and form.is_valid():
        datos = form.cleaned_data
        try:
            documento, _ = emitir_alta(
                **_base_kwargs(request, datos), contraparte=datos["contraparte"],
                contraparte_dependencia_uuid=datos["contraparte_dependencia_uuid"],
                autoriza_nombre=datos["autoriza_nombre"], autoriza_cargo=datos["autoriza_cargo"],
                datos={k: datos[k] for k in ("solicitud", "justificacion", "dictamen")},
            )
        except ValidationError as error:
            form.add_error(None, error)
        else:
            return _terminar(request, documento)
    return _render(request, "soporte_form", _contexto_form(request, form, "alta", titulo, ayuda))


@login_required
@proteger_vista(APP_SLUG, "can_view_support")
def imprimir_view(request, pk):
    dictamen = get_object_or_404(sel.dictamenes_visibles(request), documento_id=pk)
    d = dictamen.datos
    return render(request, "seguimientos_oficios/soporte_imprimir.html", {
        "dictamen": dictamen, "documento": dictamen.documento, "equipos": list(dictamen.equipos.all()), "d": d,
        "clase": dictamen.documento.clase,
        "recomendaciones": RECOMENDACIONES, "clasificaciones": CLASIFICACIONES, "disposiciones": DISPOSICIONES,
        "recomendacion_actual": d.get("recomendacion"), "clasificacion_actual": d.get("clasificacion"),
        "disposicion_actual": d.get("disposicion"),
    })
