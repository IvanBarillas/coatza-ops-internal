import uuid
from collections import Counter

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404
from django.utils.http import content_disposition_header
from django.views.decorators.clickjacking import xframe_options_sameorigin
from django.views.decorators.http import require_POST
from django.utils.http import urlencode
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.shortcuts import redirect, render
from django.urls import reverse

from .forms import AdjuntoForm, GestorEntregaForm, CategoriaForm, DocumentoEdicionForm, GestorForm, DireccionForm, NomenclaturaForm, CancelacionForm, DocumentoForm, EntregaForm, FiltroBusquedaForm, FiltroDocumentosForm
from .integracion import proteger_vista, usuarios_con_acceso
from .selectors import (
    color_semaforo, semaforo_umbrales,
    APP_SLUG, TABS, aplicar_tab, buscar_con_coincidencias, buscar_documentos, conteos_tabs, direcciones_visibles, documento_visible,
    categorias_visibles, documentos_de_gestor, gestores_asignables, documentos_seguimiento, documentos_visibles, gestores_visibles, permitido, resumen_gestores, tab_activa,
)
from .models import Adjunto, AdjuntoOCR, Categoria, Direccion, Documento, Gestor, Nomenclatura
from .storage import almacen
from .services import registrar_entrega_gestor, quitar_adjunto, roles_permitidos, editar_documento, adjuntar_pdf, cancelar_documento, crear_documento, marcar_entregado


POR_PAGINA = 25


def _sidebar_items(request):
    actual = request.resolver_match.view_name if request.resolver_match else ""
    return [
        {
            "icon": item["icon"],
            "name": item["name"],
            "href": reverse(item["url"]),
            "active": item["url"] == actual,
        }
        for item in getattr(request, "axentra_sidebar_menu", [])
    ]


def _render(request, nombre, contexto):
    contexto = {**contexto, "show_module_sidebar": True, "sidebar_items": _sidebar_items(request)}
    destino = request.headers.get("HX-Target", "")
    if request.headers.get("HX-Request") == "true":
        if destino == "workbench":
            return render(request, f"seguimientos_oficios/workbench/{nombre}.html", contexto)
        if destino == "page-content":
            return render(request, f"seguimientos_oficios/content/{nombre}.html", contexto)
    return render(request, f"seguimientos_oficios/pages/{nombre}.html", contexto)


def _query(request, *, quitar=(), **poner):
    parametros = request.GET.copy()
    for clave in ("pagina", *quitar):
        parametros.pop(clave, None)
    for clave, valor in poner.items():
        parametros[clave] = valor
    return parametros.urlencode()


@login_required
@proteger_vista(APP_SLUG, "can_view_oficios")
def documento_list_view(request):
    direcciones = direcciones_visibles(request)
    filtro = FiltroDocumentosForm(
        request.GET or None, direcciones=direcciones, gestores=gestores_visibles(request),
        categorias=categorias_visibles(request),
    )
    limpio = filtro.cleaned_data if filtro.is_valid() else {}
    todos = documentos_visibles(request)
    filtrados = buscar_documentos(todos, limpio) if limpio else todos
    tab = tab_activa(request.GET.get("tab"), bool(request.GET.get("q", "").strip()))
    conteos = conteos_tabs(filtrados)
    sin_gestor = buscar_documentos(todos, {**limpio, "gestor": ""}) if limpio else todos
    gestor_activo = request.GET.get("gestor", "")
    pagina = Paginator(aplicar_tab(filtrados, tab), POR_PAGINA).get_page(request.GET.get("pagina"))
    contexto = {
        "filtro": filtro, "pagina": pagina, "total": pagina.paginator.count, "tab": tab,
        "tabs": [
            {"clave": c, "nombre": n, "total": conteos[c], "activa": c == tab, "query": _query(request, tab=c)}
            for c, n, _ in TABS
        ],
        "gestores_resumen": [
            {"nombre": nombre, "total": total, "query": _query(request, tab="pendientes", gestor=gestor_id or "sin"),
             "activo": (gestor_id and str(gestor_id) == gestor_activo) or (gestor_id is None and gestor_activo == "sin")}
            for gestor_id, nombre, total in resumen_gestores(sin_gestor)
        ],
        "filtros_activos": any(k not in ("pagina", "tab") for k in request.GET),
        "query_sin_pagina": _query(request, tab=tab), "query_limpiar": _query(request, quitar=tuple(request.GET), tab=tab),
        "tab_explicita": request.GET.get("tab", ""),
        "varias_direcciones": direcciones.count() > 1,
    }
    return _render(request, "documento_list", contexto)


@login_required
@proteger_vista(APP_SLUG, "can_create_oficio")
def documento_create_view(request):
    direcciones = direcciones_visibles(request)
    form = DocumentoForm(
        request.POST or None, direcciones=direcciones, gestores=gestores_asignables(request),
        categorias=categorias_visibles(request),
    )
    if request.method == "POST" and form.is_valid():
        datos = form.cleaned_data
        try:
            documento = crear_documento(
                usuario=request.user, direccion=datos["direccion"], sentido=datos["sentido"],
                clase=datos["clase"], contraparte=datos["contraparte"], asunto=datos["asunto"],
                contraparte_dependencia_uuid=datos["contraparte_dependencia_uuid"],
                fecha=datos["fecha"], folio=datos["folio"],
                gestor=datos["gestor"], categoria=datos["categoria"],
            )
        except ValidationError as error:
            form.add_error(None, error)
        else:
            messages.success(request, "Documento registrado. Ya puedes adjuntar su archivo.")
            return redirect("seguimientos_oficios:documento_detail", pk=documento.pk)
    return _render(request, "documento_form", {"form": form})


_permitido = permitido


@login_required
@proteger_vista(APP_SLUG, "has_access_module")
def documento_detail_view(request, pk, entrega_form=None, cancelacion_form=None):
    documento = documento_visible(request, pk)
    contexto = {
        "documento": documento,
        "historial": documento.historial.all(),
        "entrega_form": entrega_form or EntregaForm(),
        "cancelacion_form": cancelacion_form or CancelacionForm(),
        "puede_entregar": _permitido(request, "can_update_status")
        and documento.estado == documento.Estado.GENERADO and documento.sentido == documento.Sentido.ENVIADO,
        "adjuntos": documento.adjuntos.filter(eliminado=False),
        "adjuntos_quitados": documento.adjuntos.filter(eliminado=True).order_by("eliminado_en"),
        "puede_quitar_archivos": _permitido(request, "can_remove_files") and documento.estado != documento.Estado.CANCELADO,
        "adjunto_form": AdjuntoForm(),
        "roles_adjuntables": (
            [(r, Adjunto.Rol(r).label) for r in roles_permitidos(documento)]
            if _permitido(request, "can_upload_files") else []
        ),
        "puede_cancelar": documento.estado != documento.Estado.CANCELADO and (
            _permitido(request, "can_cancel_concluded")
            if documento.estado == documento.Estado.CONCLUIDO
            else _permitido(request, "can_cancel_oficio")
        ),
    }
    return _render(request, "documento_detail", contexto)


@login_required
@require_POST
@proteger_vista(APP_SLUG, "can_update_status")
def documento_entregar_view(request, pk):
    documento = documento_visible(request, pk)
    form = EntregaForm(request.POST)
    if form.is_valid():
        try:
            marcar_entregado(documento, usuario=request.user, **form.cleaned_data)
        except ValidationError as error:
            messages.error(request, "; ".join(error.messages))
        else:
            messages.success(request, "Documento marcado como entregado.")
            return redirect("seguimientos_oficios:documento_detail", pk=pk)
    else:
        messages.error(request, "Revise los datos de la entrega.")
    return redirect("seguimientos_oficios:documento_detail", pk=pk)


@login_required
@require_POST
@proteger_vista(APP_SLUG, "can_cancel_oficio")
def documento_cancelar_view(request, pk):
    documento = documento_visible(request, pk)
    form = CancelacionForm(request.POST)
    if form.is_valid():
        try:
            cancelar_documento(
                documento, usuario=request.user, motivo=form.cleaned_data["motivo"],
                puede_cancelar_concluido=_permitido(request, "can_cancel_concluded"),
            )
        except ValidationError as error:
            messages.error(request, "; ".join(error.messages))
        else:
            messages.success(request, "Documento cancelado.")
    else:
        messages.error(request, "Indique el motivo de la cancelación (mínimo 10 caracteres).")
    return redirect("seguimientos_oficios:documento_detail", pk=pk)


@login_required
@require_POST
@proteger_vista(APP_SLUG, "can_upload_files")
def documento_adjuntar_view(request, pk):
    documento = documento_visible(request, pk)
    form = AdjuntoForm(request.POST, request.FILES)
    if form.is_valid():
        try:
            _, duplicado = adjuntar_pdf(
                documento, usuario=request.user, archivo=form.cleaned_data["archivo"], rol=form.cleaned_data["rol"] or None
            )
        except ValidationError as error:
            messages.error(request, "; ".join(error.messages))
        else:
            messages.success(request, "Archivo adjuntado.")
            if duplicado:
                messages.warning(
                    request,
                    f"Este archivo ya está en otro documento ({duplicado.documento.folio or 'sin folio'}).",
                )
    else:
        messages.error(request, "Seleccione un archivo PDF.")
    return redirect("seguimientos_oficios:documento_detail", pk=pk)


@login_required
@xframe_options_sameorigin
@proteger_vista(APP_SLUG, "has_access_module")
def adjunto_descargar_view(request, pk, adjunto_pk):
    documento = documento_visible(request, pk)
    adjunto = get_object_or_404(documento.adjuntos.filter(eliminado=False), pk=adjunto_pk)
    almacen_ = almacen()
    ruta = adjunto.ruta
    if request.GET.get("version") == "buscable":
        buscable = _ruta_buscable(adjunto)
        ruta = buscable if buscable else ruta
    if not almacen_.exists(ruta):
        raise Http404("El archivo no está en el almacén.")
    respuesta = FileResponse(almacen_.open(ruta, "rb"), content_type="application/pdf")
    respuesta["Content-Disposition"] = content_disposition_header(request.GET.get("descargar") == "1", adjunto.nombre_original)
    respuesta["X-Content-Type-Options"] = "nosniff"
    return respuesta


def _ruta_buscable(adjunto):
    """Copia con capa de texto (solo para el visor), si el OCR la generó y sigue en el almacén."""
    ruta = AdjuntoOCR.objects.filter(adjunto=adjunto).values_list("ruta_buscable", flat=True).first()
    return ruta if ruta and almacen().exists(ruta) else ""


@login_required
@proteger_vista(APP_SLUG, "can_manage_catalogs")
def catalogos_view(request):
    direcciones = Direccion.objects.order_by("nombre").prefetch_related("nomenclaturas", "gestores")
    return _render(request, "catalogos", {"direcciones": direcciones})


@login_required
@proteger_vista(APP_SLUG, "can_manage_catalogs")
def direccion_editar_view(request, pk=None):
    direccion = get_object_or_404(Direccion, pk=pk) if pk else None
    form = DireccionForm(request.POST or None, instance=direccion)
    if request.method == "POST" and form.is_valid():
        guardada = form.save()
        messages.success(request, f"Dirección {guardada.nombre} guardada.")
        return redirect("seguimientos_oficios:direccion_editar", pk=guardada.pk)
    contexto = {"form": form, "direccion": direccion}
    if direccion:
        contexto.update(
            nomenclaturas=direccion.nomenclaturas.order_by("clase"),
            nomenclatura_form=NomenclaturaForm(direccion=direccion),
            gestores=direccion.gestores.select_related("usuario").order_by("nombre"),
            usuarios=usuarios_con_acceso(APP_SLUG),
            categorias=direccion.categorias.order_by("nombre"),
        )
    return _render(request, "direccion_form", contexto)


def _volver_a_direccion(pk):
    return redirect("seguimientos_oficios:direccion_editar", pk=pk)


@login_required
@require_POST
@proteger_vista(APP_SLUG, "can_manage_catalogs")
def nomenclatura_crear_view(request, pk):
    direccion = get_object_or_404(Direccion, pk=pk)
    form = NomenclaturaForm(request.POST, direccion=direccion)
    if form.is_valid():
        nomenclatura = form.save(commit=False)
        nomenclatura.direccion = direccion
        nomenclatura.save()
        messages.success(request, f"Nomenclatura creada: {nomenclatura.ejemplo}.")
    else:
        for errores in form.errors.values():
            for error in errores:
                messages.error(request, error)
    return _volver_a_direccion(pk)


@login_required
@require_POST
@proteger_vista(APP_SLUG, "can_manage_catalogs")
def nomenclatura_actualizar_view(request, pk):
    nomenclatura = get_object_or_404(Nomenclatura, pk=pk)
    if request.POST.get("accion") == "estado":
        nomenclatura.is_active = not nomenclatura.is_active
        nomenclatura.save()
        messages.success(request, "Nomenclatura " + ("activada." if nomenclatura.is_active else "desactivada."))
    else:
        form = NomenclaturaForm(request.POST, instance=nomenclatura, direccion=nomenclatura.direccion)
        if form.is_valid():
            form.save()
            messages.success(request, f"Plantilla actualizada: {nomenclatura.ejemplo}.")
        else:
            for errores in form.errors.values():
                for error in errores:
                    messages.error(request, error)
    return _volver_a_direccion(nomenclatura.direccion_id)


@login_required
@proteger_vista(APP_SLUG, "can_edit_oficio")
def documento_editar_view(request, pk):
    documento = documento_visible(request, pk)
    inicial = {c: getattr(documento, c) for c in ("contraparte", "asunto", "fecha", "folio", "gestor", "categoria")}
    form = DocumentoEdicionForm(request.POST or None, initial=inicial, documento=documento)
    if request.method == "POST" and form.is_valid():
        datos = dict(form.cleaned_data)
        datos.pop("contraparte_dependencia", None)
        motivo = datos.pop("motivo", "")
        try:
            editar_documento(documento, usuario=request.user, cambios=datos, motivo=motivo)
        except ValidationError as error:
            form.add_error(None, error)
        else:
            messages.success(request, "Cambios guardados.")
            return redirect("seguimientos_oficios:documento_detail", pk=pk)
    return _render(request, "documento_editar", {"form": form, "documento": documento})


@login_required
@require_POST
@proteger_vista(APP_SLUG, "can_manage_catalogs")
def gestor_crear_view(request, pk):
    direccion = get_object_or_404(Direccion, pk=pk)
    form = GestorForm(request.POST, direccion=direccion)
    if form.is_valid():
        gestor = form.save(commit=False)
        gestor.direccion = direccion
        gestor.save()
        messages.success(request, f"Gestor {gestor.nombre} agregado.")
    else:
        for errores in form.errors.values():
            for error in errores:
                messages.error(request, error)
    return _volver_a_direccion(pk)


@login_required
@require_POST
@proteger_vista(APP_SLUG, "can_manage_catalogs")
def gestor_actualizar_view(request, pk):
    gestor = get_object_or_404(Gestor, pk=pk)
    if request.POST.get("accion") == "estado":
        gestor.is_active = not gestor.is_active
        gestor.save()
        messages.success(request, f"Gestor {gestor.nombre} " + ("activado." if gestor.is_active else "desactivado."))
    else:
        form = GestorForm(request.POST, instance=gestor)
        if form.is_valid():
            form.save()
            messages.success(request, "Nombre actualizado.")
        else:
            for errores in form.errors.values():
                for error in errores:
                    messages.error(request, error)
    return _volver_a_direccion(gestor.direccion_id)


@login_required
@proteger_vista(APP_SLUG, "can_view_oficios")
def busqueda_view(request):
    direcciones = direcciones_visibles(request)
    form = FiltroBusquedaForm(request.GET or None, direcciones=direcciones, categorias=categorias_visibles(request))
    limpio = form.cleaned_data if form.is_valid() else {}
    consulta = request.GET.get("q", "").strip()[:200]
    sentido = request.GET.get("sentido", "")
    if sentido not in Documento.Sentido.values:
        sentido = ""
    filtros = {c: limpio[c] for c in ("clase", "direccion", "desde", "hasta", "categoria") if limpio.get(c)}
    if sentido:
        filtros["sentido"] = sentido
    paginador, resultados = (None, [])
    if consulta:
        paginador, resultados = buscar_con_coincidencias(
            request, consulta, request.GET.get("pagina"), filtros=filtros
        )
    contexto = {
        "form": form, "consulta": consulta, "paginador": paginador, "resultados": resultados, "sentido": sentido,
        "query_sin_pagina": _query(request),
        "filtros_activos": any(request.GET.get(c) for c in ("clase", "direccion", "desde", "hasta", "categoria")),
        "query_limpiar": urlencode({"q": consulta, **({"sentido": sentido} if sentido else {})}),
        "varias_direcciones": direcciones.count() > 1,
        "ambitos": [
            {"clave": clave, "nombre": nombre, "activo": sentido == clave,
             "query": _query(request, quitar=("sentido",), **({"sentido": clave} if clave else {}))}
            for clave, nombre in (("", "Todos"), ("recibido", "Recibidos"), ("enviado", "Enviados"))
        ],
    }
    return _render(request, "busqueda", contexto)


@login_required
@proteger_vista(APP_SLUG, "has_access_module")
def visor_view(request, pk, adjunto_pk):
    documento = documento_visible(request, pk)
    adjunto = get_object_or_404(documento.adjuntos.filter(eliminado=False), pk=adjunto_pk)
    try:
        pagina = max(1, int(request.GET.get("pagina", 1)))
    except ValueError:
        pagina = 1
    consulta = request.GET.get("q", "")[:200]
    parametros = urlencode({"pagina": pagina, **({"q": consulta} if consulta else {})})
    return render(request, "seguimientos_oficios/htmx/visor.html", {
        "documento": documento, "adjunto": adjunto, "pagina": pagina,
        "src": reverse("seguimientos_oficios:lector", args=[documento.pk, adjunto.pk]) + "?" + parametros,
        "descarga": reverse("seguimientos_oficios:adjunto_descargar", args=[documento.pk, adjunto.pk]) + "?descargar=1",
    })


@login_required
@require_POST
@proteger_vista(APP_SLUG, "can_remove_files")
def adjunto_quitar_view(request, pk, adjunto_pk):
    documento = documento_visible(request, pk)
    adjunto = get_object_or_404(documento.adjuntos, pk=adjunto_pk)
    try:
        quitar_adjunto(adjunto, usuario=request.user, motivo=request.POST.get("motivo", ""))
    except ValidationError as error:
        messages.error(request, "; ".join(error.messages))
    else:
        messages.success(request, "Archivo quitado. Queda registrado en el historial.")
    return redirect("seguimientos_oficios:documento_detail", pk=pk)


@login_required
@proteger_vista(APP_SLUG, "can_view_tracking")
def seguimiento_view(request):
    todos = documentos_seguimiento(request)
    filtrados = todos
    gestor = request.GET.get("gestor", "")
    if gestor == "sin":
        filtrados = todos.filter(gestor__isnull=True)
    elif gestor:
        try:
            filtrados = todos.filter(gestor_id=uuid.UUID(gestor))
        except ValueError:
            gestor = ""
    documentos = list(filtrados)
    for documento in documentos:
        documento.dias = documento.dias_pendiente
        documento.color = color_semaforo(documento.dias)
    conteos = Counter(d.color for d in documentos)
    semaforo = request.GET.get("semaforo", "")
    if semaforo in ("verde", "ambar", "rojo"):
        documentos = [d for d in documentos if d.color == semaforo]
    else:
        semaforo = ""
    documentos.sort(key=lambda d: -d.dias)
    ambar, rojo = semaforo_umbrales()
    contexto = {
        "semaforos": [
            {"clave": c, "nombre": n, "total": conteos.get(c, 0), "activo": semaforo == c,
             "query": _query(request, quitar=("semaforo",)) if semaforo == c else _query(request, semaforo=c)}
            for c, n in (("rojo", "Rojo"), ("ambar", "Ámbar"), ("verde", "Verde"))
        ],
        "columnas": [
            {"titulo": "Por entregar", "ayuda": "Generados: ya tienen folio y aún no se entregan.",
             "documentos": [d for d in documentos if d.estado == Documento.Estado.GENERADO]},
            {"titulo": "Entregados sin evidencia", "ayuda": "Ya se entregaron; falta subir la evidencia.",
             "documentos": [d for d in documentos if d.estado == Documento.Estado.ENTREGADO]},
        ],
        "gestores_resumen": [
            {"nombre": nombre, "total": total, "query": _query(request, gestor=gestor_id or "sin"),
             "activo": (gestor_id and str(gestor_id) == gestor) or (gestor_id is None and gestor == "sin")}
            for gestor_id, nombre, total in resumen_gestores(todos)
        ],
        "filtrado": bool(gestor or semaforo), "query_limpiar": "",
        "umbral_ambar": ambar, "umbral_rojo": rojo, "total": len(documentos),
    }
    return _render(request, "seguimiento", contexto)


@login_required
@xframe_options_sameorigin
@proteger_vista(APP_SLUG, "has_access_module")
def lector_pdf_view(request, pk, adjunto_pk):
    """Página del visor PDF.js: abre en la página indicada y resalta las palabras buscadas."""
    documento = documento_visible(request, pk)
    adjunto = get_object_or_404(documento.adjuntos.filter(eliminado=False), pk=adjunto_pk)
    try:
        pagina = max(1, int(request.GET.get("pagina", 1)))
    except ValueError:
        pagina = 1
    url = reverse("seguimientos_oficios:adjunto_descargar", args=[documento.pk, adjunto.pk])
    if _ruta_buscable(adjunto):
        url += "?version=buscable"
    return render(request, "seguimientos_oficios/visor_pdf.html", {
        "adjunto": adjunto, "pagina": pagina, "consulta": request.GET.get("q", "")[:200], "url_pdf": url,
    })


@login_required
@require_POST
@proteger_vista(APP_SLUG, "can_manage_catalogs")
def categoria_crear_view(request, pk):
    direccion = get_object_or_404(Direccion, pk=pk)
    form = CategoriaForm(request.POST, direccion=direccion)
    if form.is_valid():
        categoria = form.save(commit=False)
        categoria.direccion = direccion
        categoria.save()
        messages.success(request, f"Categoría {categoria.nombre} agregada.")
    else:
        for errores in form.errors.values():
            for error in errores:
                messages.error(request, error)
    return _volver_a_direccion(pk)


@login_required
@require_POST
@proteger_vista(APP_SLUG, "can_manage_catalogs")
def categoria_actualizar_view(request, pk):
    categoria = get_object_or_404(Categoria, pk=pk)
    if request.POST.get("accion") == "estado":
        categoria.is_active = not categoria.is_active
        categoria.save()
        messages.success(request, f"Categoría {categoria.nombre} " + ("activada." if categoria.is_active else "desactivada."))
    else:
        form = CategoriaForm(request.POST, instance=categoria)
        if form.is_valid():
            form.save()
            messages.success(request, "Nombre actualizado.")
        else:
            for errores in form.errors.values():
                for error in errores:
                    messages.error(request, error)
    return _volver_a_direccion(categoria.direccion_id)


@login_required
@proteger_vista(APP_SLUG, "has_access_module")
def inicio_view(request):
    """Entrada del módulo (la que abre el Hub): lleva a cada persona a la vista que su rol permite."""
    for llave, destino in (
        ("can_view_oficios", "documento_list"), ("can_view_tracking", "seguimiento"), ("can_view_own_pendings", "gestor"),
    ):
        if permitido(request, llave):
            return redirect(f"seguimientos_oficios:{destino}")
    raise PermissionDenied


@login_required
@proteger_vista(APP_SLUG, "can_view_own_pendings")
def gestor_view(request):
    """Vista pensada para el celular del gestor: sus pendientes, con la entrega y el acuse a un paso."""
    vinculado = Gestor.objects.filter(usuario=request.user, is_active=True, is_deleted=False).exists()
    documentos = list(documentos_de_gestor(request))
    for documento in documentos:
        documento.dias = documento.dias_pendiente
        documento.color = color_semaforo(documento.dias)
    documentos.sort(key=lambda d: -d.dias)
    return _render(request, "gestor", {
        "documentos": documentos, "vinculado": vinculado, "entrega_form": GestorEntregaForm(),
        "puede_registrar": _permitido(request, "can_register_own_delivery"),
    })


@login_required
@require_POST
@proteger_vista(APP_SLUG, "can_register_own_delivery")
def gestor_entrega_view(request, pk):
    documento = get_object_or_404(documentos_de_gestor(request), pk=pk)
    form = GestorEntregaForm(request.POST, request.FILES)
    if form.is_valid():
        try:
            resultado = registrar_entrega_gestor(
                documento, usuario=request.user, fecha_entrega=form.cleaned_data["fecha_entrega"],
                receptor=form.cleaned_data["receptor"], archivo=form.cleaned_data["archivo"],
            )
        except ValidationError as error:
            messages.error(request, "; ".join(error.messages))
        else:
            messages.success(
                request,
                "Listo: el oficio quedó concluido." if resultado.estado == Documento.Estado.CONCLUIDO
                else "Entrega registrada. Falta subir el acuse.",
            )
    else:
        messages.error(request, "Revise los datos de la entrega.")
    return redirect("seguimientos_oficios:gestor")
