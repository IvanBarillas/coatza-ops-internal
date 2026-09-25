from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db.models import Prefetch, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from ..integracion import proteger_vista
from ..models import Bien, PrestamoBien
from ..selectors import APP_SLUG, gestores_asignables, permitido
from ..views import _query, _render
from . import selectors as sel
from .forms import BienForm, DevolucionForm, ValeForm
from .services import crear_vale, registrar_devolucion

GRUPOS_PRESTAMOS = {
    "abiertos": ("Abiertos", lambda p: p.situacion in ("vigente", "por_vencer", "vencido")),
    "vencidos": ("Vencidos", lambda p: p.situacion == "vencido"),
    "devueltos": ("Devueltos", lambda p: p.situacion == "devuelto"),
    "todos": ("Todos", lambda p: True),
}


@login_required
@proteger_vista(APP_SLUG, "can_view_loans")
def prestamos_view(request):
    prestamos = list(sel.prestamos_visibles(request).order_by("fecha_limite"))
    tab = request.GET.get("tab", "abiertos")
    if tab not in GRUPOS_PRESTAMOS:
        tab = "abiertos"
    conteos = {clave: sum(1 for p in prestamos if regla(p)) for clave, (_, regla) in GRUPOS_PRESTAMOS.items()}
    filas = [p for p in prestamos if GRUPOS_PRESTAMOS[tab][1](p)]
    pagina = Paginator(filas, 25).get_page(request.GET.get("pagina"))
    return _render(request, "prestamos", {
        "pagina": pagina, "tab": tab, "total": len(filas),
        "tabs": [
            {"clave": c, "nombre": n, "total": conteos[c], "activa": c == tab, "query": _query(request, tab=c)}
            for c, (n, _) in GRUPOS_PRESTAMOS.items()
        ],
        "query_sin_pagina": _query(request, tab=tab),
        "puede_gestionar": permitido(request, "can_manage_loans"),
    })


@login_required
@proteger_vista(APP_SLUG, "can_manage_loans")
def vale_crear_view(request):
    direcciones = sel.direcciones_con_vales(request, "can_manage_loans")
    if not direcciones.exists():
        return _render(request, "vale_form", {"form": None})
    bienes = sel.bienes_disponibles(request)
    form = ValeForm(request.POST or None, direcciones=direcciones, bienes=bienes, gestores=gestores_asignables(request))
    if request.method == "POST" and form.is_valid():
        datos = form.cleaned_data
        try:
            documento, _ = crear_vale(
                usuario=request.user, direccion=datos["direccion"], bienes=datos["bienes"],
                fecha_entrega=datos["fecha_entrega"], fecha_limite=datos["fecha_limite"],
                contraparte=datos["contraparte"], contraparte_dependencia_uuid=datos["contraparte_dependencia_uuid"],
                gestor=datos["gestor"], observaciones=datos["observaciones"],
            )
        except ValidationError as error:
            form.add_error(None, error)
        else:
            messages.success(request, f"Vale {documento.folio} generado. Ya puedes imprimirlo para firmarlo.")
            return redirect("seguimientos_oficios:documento_detail", pk=documento.pk)
    return _render(request, "vale_form", {"form": form, "sin_bienes": not bienes.exists()})


@login_required
@proteger_vista(APP_SLUG, "can_view_loans")
def vale_imprimir_view(request, pk):
    prestamo = get_object_or_404(sel.prestamos_visibles(request), documento_id=pk)
    return render(request, "seguimientos_oficios/vale_imprimir.html", {
        "prestamo": prestamo, "documento": prestamo.documento,
        "bienes": [r.bien for r in prestamo.renglones.select_related("bien")],
    })


@login_required
@require_POST
@proteger_vista(APP_SLUG, "can_manage_loans")
def devolucion_view(request, pk):
    prestamo = get_object_or_404(sel.prestamos_visibles(request), documento_id=pk)
    form = DevolucionForm(request.POST)
    if form.is_valid():
        try:
            registrar_devolucion(prestamo, usuario=request.user, fecha=form.cleaned_data["fecha"], observaciones=form.cleaned_data["observaciones"])
        except ValidationError as error:
            messages.error(request, "; ".join(error.messages))
        else:
            messages.success(request, "Devolución registrada: los bienes vuelven a estar disponibles.")
    else:
        messages.error(request, "Revise los datos de la devolución.")
    return redirect("seguimientos_oficios:documento_detail", pk=pk)


SITUACIONES_BIEN = (
    ("todos", "Todos"), ("disponible", "Disponibles"), ("prestado", "Prestados"),
    ("en_reparacion", "En reparación"), ("baja", "Baja"),
)


@login_required
@proteger_vista(APP_SLUG, "can_view_loans")
def bienes_view(request):
    abiertos = PrestamoBien.objects.filter(abierto=True).select_related("prestamo__documento")
    bienes = list(
        sel.bienes_visibles(request)
        .prefetch_related(Prefetch("asignaciones", queryset=abiertos, to_attr="abiertas"))
        .order_by("nombre", "identificador")
    )
    texto = request.GET.get("q", "").strip()[:100].casefold()
    if texto:
        bienes = [b for b in bienes if texto in f"{b.nombre} {b.identificador} {b.folio_inventario}".casefold()]
    for bien in bienes:
        bien.situacion = "prestado" if bien.abiertas else bien.estado
        bien.prestamo_abierto = bien.abiertas[0].prestamo if bien.abiertas else None
    situacion = request.GET.get("situacion", "todos")
    if situacion not in dict(SITUACIONES_BIEN):
        situacion = "todos"
    conteos = {c: sum(1 for b in bienes if c == "todos" or b.situacion == c) for c, _ in SITUACIONES_BIEN}
    filas = [b for b in bienes if situacion == "todos" or b.situacion == situacion]
    pagina = Paginator(filas, 25).get_page(request.GET.get("pagina"))
    return _render(request, "bienes", {
        "pagina": pagina, "situacion": situacion, "texto": request.GET.get("q", ""), "total": len(filas),
        "tabs": [
            {"clave": c, "nombre": n, "total": conteos[c], "activa": c == situacion, "query": _query(request, situacion=c)}
            for c, n in SITUACIONES_BIEN
        ],
        "query_sin_pagina": _query(request, situacion=situacion),
        "puede_gestionar": permitido(request, "can_manage_loans"),
    })


@login_required
@proteger_vista(APP_SLUG, "can_manage_loans")
def bien_form_view(request, pk=None):
    direcciones = sel.direcciones_con_vales(request, "can_manage_loans")
    bien = get_object_or_404(sel.bienes_visibles(request), pk=pk) if pk else None
    form = BienForm(request.POST or None, instance=bien, direcciones=direcciones)
    if request.method == "POST" and form.is_valid():
        guardado = form.save()
        messages.success(request, f"Bien {guardado} guardado.")
        return redirect("seguimientos_oficios:bienes")
    return _render(request, "bien_form", {"form": form, "bien": bien, "sin_habilitar": not direcciones.exists()})
