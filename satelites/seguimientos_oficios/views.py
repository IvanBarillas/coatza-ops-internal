from django.contrib import messages
from django.core.paginator import Paginator
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404
from django.utils.http import content_disposition_header
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.shortcuts import redirect, render
from django.urls import reverse

from .forms import AdjuntoForm, BandejaConfigForm, DireccionForm, NomenclaturaForm, CancelacionForm, DocumentoForm, EntregaForm, FiltroDocumentosForm
from .integracion import proteger_vista
from .selectors import APP_SLUG, buscar_documentos, direcciones_visibles, documento_visible, documentos_visibles
from . import bandeja
from .models import Direccion, Nomenclatura
from .storage import almacen
from .services import adjuntar_desde_bandeja, adjuntar_pdf, listar_bandeja, ruta_bandeja_de, cancelar_documento, crear_documento, marcar_entregado


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


@login_required
@proteger_vista(APP_SLUG, "can_view_oficios")
def documento_list_view(request):
    direcciones = direcciones_visibles(request)
    filtro = FiltroDocumentosForm(request.GET or None, direcciones=direcciones)
    documentos = documentos_visibles(request)
    if filtro.is_valid():
        documentos = buscar_documentos(documentos, filtro.cleaned_data)
    pagina = Paginator(documentos, POR_PAGINA).get_page(request.GET.get("pagina"))
    parametros = request.GET.copy()
    parametros.pop("pagina", None)
    contexto = {
        "filtro": filtro, "pagina": pagina, "total": pagina.paginator.count,
        "filtros_activos": bool(parametros), "query_sin_pagina": parametros.urlencode(),
        "varias_direcciones": direcciones.count() > 1,
    }
    return _render(request, "documento_list", contexto)


@login_required
@proteger_vista(APP_SLUG, "can_create_oficio")
def documento_create_view(request):
    direcciones = direcciones_visibles(request)
    form = DocumentoForm(request.POST or None, direcciones=direcciones)
    if request.method == "POST" and form.is_valid():
        datos = form.cleaned_data
        try:
            crear_documento(
                usuario=request.user, direccion=datos["direccion"], sentido=datos["sentido"],
                clase=datos["clase"], contraparte=datos["contraparte"], asunto=datos["asunto"],
                fecha=datos["fecha"], folio=datos["folio"], director_nombre=datos["director_nombre"],
            )
        except ValidationError as error:
            form.add_error(None, error)
        else:
            messages.success(request, "Documento registrado.")
            return redirect("seguimientos_oficios:documento_list")
    return _render(request, "documento_form", {"form": form})


def _permitido(request, llave):
    return request.axentra_is_root or llave in request.axentra_permissions_list


@login_required
@proteger_vista(APP_SLUG, "can_view_oficios")
def documento_detail_view(request, pk, entrega_form=None, cancelacion_form=None):
    documento = documento_visible(request, pk)
    contexto = {
        "documento": documento,
        "historial": documento.historial.all(),
        "entrega_form": entrega_form or EntregaForm(),
        "cancelacion_form": cancelacion_form or CancelacionForm(),
        "puede_entregar": _permitido(request, "can_update_status")
        and documento.estado == documento.Estado.GENERADO and documento.sentido == documento.Sentido.ENVIADO,
        "adjuntos": documento.adjuntos.all(),
        "adjunto_form": AdjuntoForm(),
        "puede_adjuntar": _permitido(request, "can_upload_files") and (
            documento.estado == documento.Estado.REGISTRADO
            if documento.sentido == documento.Sentido.RECIBIDO
            else documento.estado in (documento.Estado.ENTREGADO, documento.Estado.CONCLUIDO)
        ),
        "bandeja_configurada": bool(ruta_bandeja_de(documento)),
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
            _, duplicado = adjuntar_pdf(documento, usuario=request.user, archivo=form.cleaned_data["archivo"])
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
@proteger_vista(APP_SLUG, "can_view_oficios")
def adjunto_descargar_view(request, pk, adjunto_pk):
    documento = documento_visible(request, pk)
    adjunto = get_object_or_404(documento.adjuntos, pk=adjunto_pk)
    almacen_ = almacen()
    if not almacen_.exists(adjunto.ruta):
        raise Http404("El archivo no está en el almacén.")
    respuesta = FileResponse(almacen_.open(adjunto.ruta, "rb"), content_type="application/pdf")
    respuesta["Content-Disposition"] = content_disposition_header(False, adjunto.nombre_original)
    respuesta["X-Content-Type-Options"] = "nosniff"
    return respuesta


@login_required
@proteger_vista(APP_SLUG, "can_upload_files")
def documento_bandeja_view(request, pk):
    documento = documento_visible(request, pk)
    try:
        archivos, error = listar_bandeja(documento), ""
    except ValidationError as excepcion:
        archivos, error = [], "; ".join(excepcion.messages)
    return render(request, "seguimientos_oficios/htmx/bandeja_lista.html",
                  {"documento": documento, "archivos": archivos, "error": error})


@login_required
@require_POST
@proteger_vista(APP_SLUG, "can_upload_files")
def documento_adjuntar_bandeja_view(request, pk):
    documento = documento_visible(request, pk)
    try:
        _, duplicado = adjuntar_desde_bandeja(documento, usuario=request.user, nombre=request.POST.get("nombre", ""))
    except ValidationError as error:
        messages.error(request, "; ".join(error.messages))
    else:
        messages.success(request, "Archivo adjuntado desde la bandeja.")
        if duplicado:
            messages.warning(request, f"Este archivo ya está en otro documento ({duplicado.documento.folio or 'sin folio'}).")
    return redirect("seguimientos_oficios:documento_detail", pk=pk)


def _estado_bandeja(ruta):
    if not ruta:
        return {"ruta": "", "ok": None, "detalle": "Sin configurar"}
    try:
        return {"ruta": ruta, "ok": True, "detalle": f"{len(bandeja.listar_pdfs(bandeja.resolver(ruta)))} PDF"}
    except bandeja.BandejaError as error:
        return {"ruta": ruta, "ok": False, "detalle": str(error)}


@login_required
@proteger_vista(APP_SLUG, "can_configure_bandeja")
def configuracion_view(request):
    filas = []
    for direccion in direcciones_visibles(request):
        filas.append({
            "direccion": direccion,
            "form": BandejaConfigForm(initial={
                "ruta_recibidos": direccion.ruta_recibidos, "ruta_evidencias": direccion.ruta_evidencias,
            }),
            "recibidos": _estado_bandeja(direccion.ruta_recibidos),
            "evidencias": _estado_bandeja(direccion.ruta_evidencias),
        })
    raiz = bandeja.raiz()
    return _render(request, "configuracion", {"filas": filas, "raiz": str(raiz) if raiz else ""})


@login_required
@require_POST
@proteger_vista(APP_SLUG, "can_configure_bandeja")
def configuracion_guardar_view(request, pk):
    direccion = get_object_or_404(direcciones_visibles(request), pk=pk)
    form = BandejaConfigForm(request.POST)
    if form.is_valid():
        direccion.ruta_recibidos = form.cleaned_data["ruta_recibidos"]
        direccion.ruta_evidencias = form.cleaned_data["ruta_evidencias"]
        direccion.save()
        messages.success(request, f"Bandeja de {direccion.nombre} guardada.")
    else:
        for errores in form.errors.values():
            for error in errores:
                messages.error(request, f"{direccion.nombre}: {error}")
    return redirect("seguimientos_oficios:configuracion")


@login_required
@proteger_vista(APP_SLUG, "can_manage_catalogs")
def catalogos_view(request):
    direcciones = Direccion.objects.order_by("nombre").prefetch_related("nomenclaturas")
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
