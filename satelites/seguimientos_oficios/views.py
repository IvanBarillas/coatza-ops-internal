from django.contrib import messages
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.shortcuts import redirect, render
from django.urls import reverse

from .forms import CancelacionForm, DocumentoForm, EntregaForm
from .integracion import proteger_vista
from .selectors import APP_SLUG, direcciones_visibles, documento_visible, documentos_visibles
from .services import cancelar_documento, crear_documento, marcar_entregado


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
    return _render(request, "documento_list", {"documentos": documentos_visibles(request)[:200]})


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
