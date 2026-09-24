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

from .forms import AdjuntoForm, CancelacionForm, DocumentoForm, EntregaForm, FiltroDocumentosForm
from .integracion import proteger_vista
from .selectors import APP_SLUG, buscar_documentos, direcciones_visibles, documento_visible, documentos_visibles
from .storage import almacen
from .services import adjuntar_pdf, cancelar_documento, crear_documento, marcar_entregado


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
