from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render

from ..integracion import nombre_de_usuario, proteger_vista
from ..models import ClaseDocumento, Direccion, Documento, Gestor
from ..selectors import APP_SLUG, gestores_asignables, permitido
from ..views import _query, _render
from . import selectors as sel
from .forms import AltaForm, BajaForm, DiagnosticoForm, ResguardoForm, leer_componentes, leer_equipos, leer_equipos_edicion
from .services import (
    CLASIFICACIONES, COMPONENTES, DISPOSICIONES, RECOMENDACIONES, edicion_exige_motivo, editar_dictamen, emitir_alta, emitir_baja,
    emitir_diagnostico, emitir_resguardo,
)

TABS = (
    ("todos", "Todos", None),
    ("diagnosticos", "Diagnósticos", ClaseDocumento.DIAGNOSTICO_TECNICO),
    ("bajas", "Bajas", ClaseDocumento.DICTAMEN_BAJA),
    ("altas", "Altas", ClaseDocumento.DICTAMEN_ALTA),
    ("resguardos", "Resguardos", ClaseDocumento.RESGUARDO),
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


def _datos_diagnostico(d):
    return {
        "fecha_recibido": d["fecha_recibido"].isoformat(), "tipo_bien": d["tipo_bien"], "fallo": d["fallo"], "causa": d["causa"],
        "solucion": d["solucion"], "observaciones": d["observaciones"], "recomendacion": d["recomendacion"],
        "solicito": d["solicitante"],
    }


def _datos_baja(d):
    return {"diagnostico": d["diagnostico"], "clasificacion": d["clasificacion"], "disposicion": d["disposicion"], "solicito": d["solicitante"]}


def _datos_resguardo(d):
    return {"empleado": d["empleado"], "fecha_entrega": d["fecha_entrega"].isoformat()}


def _datos_alta(d):
    return {k: d[k] for k in ("solicitud", "justificacion", "dictamen")}


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
        "gestor": datos.get("gestor"),
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
    form = DiagnosticoForm(request.POST or None, direcciones=direcciones, gestores=gestores_asignables(request))
    equipos, errores = [{}], []
    if request.method == "POST":
        equipos, errores = leer_equipos(request.POST, sel.bienes_catalogo(request))
        if form.is_valid() and not errores:
            datos = form.cleaned_data
            try:
                documento, _ = emitir_diagnostico(
                    **_base_kwargs(request, datos), solicitante=datos["solicitante"], equipo=(equipos or [{}])[0],
                    datos=_datos_diagnostico(datos),
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
    form = BajaForm(request.POST or None, direcciones=direcciones, gestores=gestores_asignables(request))
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
                    datos=_datos_baja(datos),
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
    form = AltaForm(request.POST or None, direcciones=direcciones, gestores=gestores_asignables(request))
    if request.method == "POST" and form.is_valid():
        datos = form.cleaned_data
        try:
            documento, _ = emitir_alta(
                **_base_kwargs(request, datos), contraparte=datos["contraparte"],
                contraparte_dependencia_uuid=datos["contraparte_dependencia_uuid"],
                autoriza_nombre=datos["autoriza_nombre"], autoriza_cargo=datos["autoriza_cargo"],
                datos=_datos_alta(datos),
            )
        except ValidationError as error:
            form.add_error(None, error)
        else:
            return _terminar(request, documento)
    return _render(request, "soporte_form", _contexto_form(request, form, "alta", titulo, ayuda))


def _filas_de_componentes(filas=None):
    """Los cuatro renglones fijos del resguardo, con lo ya capturado (por tipo) o en blanco."""
    por_tipo = {f.get("tipo"): f for f in filas or []}
    return [
        {"id": por_tipo.get(t, {}).get("id", ""), "tipo": t, "equipo": nombre, "marca_modelo": por_tipo.get(t, {}).get("marca_modelo", ""),
         "serie": por_tipo.get(t, {}).get("serie", ""), "folio_inventario": por_tipo.get(t, {}).get("folio_inventario", ""),
         "info_tecnica": por_tipo.get(t, {}).get("info_tecnica", ""), "departamento": "", "bien": por_tipo.get(t, {}).get("bien", "")}
        for t, nombre in COMPONENTES
    ]


@login_required
@proteger_vista(APP_SLUG, "can_manage_support")
def crear_resguardo_view(request):
    direcciones = sel.direcciones_con_soporte(request, "can_manage_support")
    titulo, ayuda = "Nuevo resguardo de equipo", "Equipo de cómputo que se entrega a un empleado, con su monitor, teclado y ratón."
    if not direcciones.exists():
        return _render(request, "soporte_form", _contexto_form(request, None, "resguardo", titulo, ayuda))
    form = ResguardoForm(request.POST or None, direcciones=direcciones, gestores=gestores_asignables(request))
    filas, errores = _filas_de_componentes(), []
    if request.method == "POST":
        componentes, errores = leer_componentes(request.POST, sel.bienes_catalogo(request))
        filas = _filas_de_componentes([{**c, "bien": c["bien"].pk if c.get("bien") else ""} for c in componentes])
        if form.is_valid() and not errores:
            datos = form.cleaned_data
            try:
                documento, _ = emitir_resguardo(
                    **_base_kwargs(request, datos), contraparte=datos["contraparte"],
                    contraparte_dependencia_uuid=datos["contraparte_dependencia_uuid"], equipos=componentes,
                    autoriza_nombre=datos["autoriza_nombre"], autoriza_cargo=datos["autoriza_cargo"],
                    fecha=datos["fecha_entrega"], datos=_datos_resguardo(datos),
                )
            except ValidationError as error:
                form.add_error(None, error)
            else:
                return _terminar(request, documento)
    return _render(request, "soporte_form", _contexto_form(request, form, "resguardo", titulo, ayuda, filas, False, errores))


@login_required
@proteger_vista(APP_SLUG, "can_view_support")
def imprimir_view(request, pk):
    dictamen = get_object_or_404(sel.dictamenes_visibles(request), documento_id=pk)
    d = dictamen.datos
    equipos = list(dictamen.equipos.all())
    return render(request, "seguimientos_oficios/soporte_imprimir.html", {
        "dictamen": dictamen, "documento": dictamen.documento, "equipos": equipos, "d": d,
        "clase": dictamen.documento.clase,
        "componentes": [(nombre, next((e for e in equipos if e.tipo == tipo), None)) for tipo, nombre in COMPONENTES],
        "recomendaciones": RECOMENDACIONES, "clasificaciones": CLASIFICACIONES, "disposiciones": DISPOSICIONES,
        "recomendacion_actual": d.get("recomendacion"), "clasificacion_actual": d.get("clasificacion"),
        "disposicion_actual": d.get("disposicion"),
    })


FORMULARIOS = {
    ClaseDocumento.DIAGNOSTICO_TECNICO: (DiagnosticoForm, "diagnostico", _datos_diagnostico),
    ClaseDocumento.DICTAMEN_BAJA: (BajaForm, "baja", _datos_baja),
    ClaseDocumento.DICTAMEN_ALTA: (AltaForm, "alta", _datos_alta),
    ClaseDocumento.RESGUARDO: (ResguardoForm, "resguardo", _datos_resguardo),
}


def _inicial(dictamen):
    documento, d = dictamen.documento, dictamen.datos
    inicial = {
        "ticket": dictamen.ticket, "elaboro_cargo": dictamen.elaboro_cargo, "autoriza_nombre": dictamen.autoriza_nombre,
        "autoriza_cargo": dictamen.autoriza_cargo, "direccion": documento.direccion_id, "gestor": documento.gestor_id,
        "solicitante": d.get("solicito", documento.contraparte), "fecha_recibido": d.get("fecha_recibido"),
        **{k: v for k, v in d.items() if k not in ("solicito", "fecha_recibido")},
    }
    if documento.clase == ClaseDocumento.RESGUARDO:
        inicial["fecha_entrega"] = d.get("fecha_entrega")
    if documento.clase == ClaseDocumento.DIAGNOSTICO_TECNICO:
        inicial["solicitante"] = documento.contraparte
    elif documento.contraparte_dependencia_uuid:
        inicial["contraparte_dependencia"] = str(documento.contraparte_dependencia_uuid)
    else:
        inicial["contraparte"] = documento.contraparte
    return inicial


@login_required
@proteger_vista(APP_SLUG, "can_manage_support")
def editar_view(request, pk):
    dictamen = get_object_or_404(sel.dictamenes_visibles(request, "can_manage_support"), documento_id=pk)
    documento = dictamen.documento
    formulario, clase_ctx, armar_datos = FORMULARIOS[documento.clase]
    direcciones = Direccion.objects.filter(pk=documento.direccion_id)
    form = formulario(request.POST or None, direcciones=direcciones, edicion=True, initial=_inicial(dictamen),
                        gestores=Gestor.objects.filter(Q(pk__in=gestores_asignables(request).values("pk")) | Q(pk=documento.gestor_id)))
    filas = [
        {"id": str(r.pk), "equipo": r.equipo, "marca_modelo": r.marca_modelo, "serie": r.serie,
         "folio_inventario": r.folio_inventario, "departamento": r.departamento, "bien": str(r.bien_id or ""),
         "tipo": r.tipo, "info_tecnica": r.info_tecnica}
        for r in dictamen.equipos.all()
    ]
    errores = []
    if request.method == "POST":
        nuevos = leer_equipos_edicion(request.POST)
        if nuevos:
            filas = [{**f, **nuevos.get(f["id"], {})} for f in filas]
        if form.is_valid():
            datos = form.cleaned_data
            try:
                editar_dictamen(
                    dictamen, usuario=request.user, motivo=datos.get("motivo", ""),
                    campos={"ticket": datos["ticket"], "elaboro_cargo": datos["elaboro_cargo"],
                            "autoriza_nombre": datos.get("autoriza_nombre", ""), "autoriza_cargo": datos.get("autoriza_cargo", "")},
                    datos=armar_datos(datos), equipos=nuevos,
                    contraparte=datos.get("solicitante") if documento.clase == ClaseDocumento.DIAGNOSTICO_TECNICO else datos.get("contraparte"),
                    contraparte_dependencia_uuid=datos.get("contraparte_dependencia_uuid"), gestor=datos.get("gestor"),
                )
            except ValidationError as error:
                form.add_error(None, error)
            else:
                messages.success(request, f"{documento.get_clase_display()} {documento.folio} corregido. Vuelve a imprimirlo si ya estaba impreso.")
                return redirect("seguimientos_oficios:documento_detail", pk=documento.pk)
    contexto = _contexto_form(request, form, clase_ctx, f"Corregir {documento.get_clase_display().lower()}", f"Folio {documento.folio}: el folio, la dirección y los bienes que ampara no cambian.", filas, documento.clase == ClaseDocumento.DIAGNOSTICO_TECNICO, errores)
    contexto.update(
        editando=True, documento=documento, sin_habilitar=False,
        aviso_firmado=edicion_exige_motivo(documento) or documento.estado != Documento.Estado.GENERADO,
    )
    return _render(request, "soporte_form", contexto)
