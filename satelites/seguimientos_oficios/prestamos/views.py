from collections import Counter

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Prefetch
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from ..integracion import proteger_vista
from ..models import Bien, CategoriaBien, PrestamoBien
from ..selectors import APP_SLUG, gestores_asignables, permitido
from ..views import _query, _render
from . import selectors as sel
from .forms import BienForm, DevolucionForm, ValeEdicionForm, ValeForm
from .services import crear_vale, editar_vale, foto_bien, registrar_alta_bien, registrar_cambios_bien, registrar_devolucion

GRUPOS_PRESTAMOS = {
    "abiertos": ("Abiertos", lambda p: p.situacion in ("vigente", "por_vencer", "vencido")),
    "vencidos": ("Vencidos", lambda p: p.situacion == "vencido"),
    "devueltos": ("Devueltos", lambda p: p.situacion == "devuelto"),
    "todos": ("Todos", lambda p: True),
}


@login_required
@proteger_vista(APP_SLUG, "can_view_loans")
def vales_view(request):
    prestamos = list(sel.prestamos_visibles(request).order_by("fecha_limite"))
    tab = request.GET.get("tab", "abiertos")
    if tab not in GRUPOS_PRESTAMOS:
        tab = "abiertos"
    conteos = {clave: sum(1 for p in prestamos if regla(p)) for clave, (_, regla) in GRUPOS_PRESTAMOS.items()}
    filas = [p for p in prestamos if GRUPOS_PRESTAMOS[tab][1](p)]
    pagina = Paginator(filas, 25).get_page(request.GET.get("pagina"))
    return _render(request, "vales", {
        "pagina": pagina, "tab": tab, "total": len(filas),
        "tabs": [
            {"clave": c, "nombre": n, "total": conteos[c], "activa": c == tab, "query": _query(request, tab=c)}
            for c, (n, _) in GRUPOS_PRESTAMOS.items()
        ],
        "query_sin_pagina": _query(request, tab=tab),
        "puede_gestionar": permitido(request, "can_manage_loans"),
    })


COLORES_PRESTAMO = {"vencido": "rojo", "por_vencer": "ambar", "vigente": "verde"}


@login_required
@proteger_vista(APP_SLUG, "can_view_loans")
def prestamos_view(request):
    """Seguimiento de préstamos: los abiertos con semáforo por fecha límite, los que más urgen primero."""
    from ..integracion import valor_entorno

    abiertos = [p for p in sel.prestamos_visibles(request).order_by("fecha_limite") if p.situacion in COLORES_PRESTAMO]
    for prestamo in abiertos:
        prestamo.color = COLORES_PRESTAMO[prestamo.situacion]
    conteos = Counter(p.color for p in abiertos)
    color = request.GET.get("color", "")
    color = color if color in ("rojo", "ambar", "verde") else ""
    return _render(request, "prestamos", {
        "prestamos": [p for p in abiertos if not color or p.color == color],
        "tiles": [
            {"clave": c, "nombre": n, "ayuda": a, "total": conteos.get(c, 0), "activo": color == c,
             "query": _query(request, quitar=("color",)) if color == c else _query(request, color=c)}
            for c, n, a in (("rojo", "Vencidos", "Pasó la fecha límite"), ("ambar", "Por vencer", "Vencen pronto"), ("verde", "Vigentes", "Con tiempo"))
        ],
        "total_abiertos": len(abiertos), "filtrado": bool(color),
        "aviso_dias": valor_entorno("OFICIOS_PRESTAMO_AVISO_DIAS", "3"),
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
    return _render(request, "vale_form", {
        "form": form, "sin_bienes": not bienes.exists(),
        "bienes_data": [
            {"id": str(b.pk), "texto": str(b), "categoria": str(b.categoria_id or ""), "direccion": str(b.direccion_id)}
            for b in bienes.select_related("categoria")
        ],
        "categorias_data": [
            {"id": str(c.pk), "nombre": c.nombre, "direccion": str(c.direccion_id)}
            for c in CategoriaBien.objects.filter(direccion__in=direcciones, is_active=True, is_deleted=False).order_by("nombre")
        ],
        "elegidos": [str(v) for v in request.POST.getlist("bienes")] if request.method == "POST" else [],
    })


@login_required
@proteger_vista(APP_SLUG, "can_view_loans")
def vale_imprimir_view(request, pk):
    prestamo = get_object_or_404(sel.prestamos_visibles(request), documento_id=pk)
    bienes = [r.bien for r in prestamo.renglones.select_related("bien")]
    return render(request, "seguimientos_oficios/vale_imprimir.html", {
        "prestamo": prestamo, "documento": prestamo.documento, "bienes": bienes,
        "relleno": range(max(0, 9 - len(bienes))),
    })


@login_required
@proteger_vista(APP_SLUG, "can_manage_loans")
def vale_editar_view(request, pk):
    from ..soporte.services import edicion_exige_motivo

    prestamo = get_object_or_404(sel.prestamos_visibles(request, "can_manage_loans"), documento_id=pk)
    documento = prestamo.documento
    form = ValeEdicionForm(request.POST or None, prestamo=prestamo)
    if request.method == "POST" and form.is_valid():
        datos = form.cleaned_data
        try:
            editar_vale(
                prestamo, usuario=request.user, fecha_entrega=datos["fecha_entrega"], fecha_limite=datos["fecha_limite"],
                observaciones=datos["observaciones"], contraparte=datos["contraparte"],
                contraparte_dependencia_uuid=datos["contraparte_dependencia_uuid"], motivo=datos["motivo"],
            )
        except ValidationError as error:
            form.add_error(None, error)
        else:
            messages.success(request, f"Vale {documento.folio} corregido. Vuelve a imprimirlo si ya estaba impreso.")
            return redirect("seguimientos_oficios:documento_detail", pk=documento.pk)
    return _render(request, "vale_editar", {
        "form": form, "prestamo": prestamo, "documento": documento, "area_actual": "prestamos",
        "aviso_firmado": edicion_exige_motivo(documento),
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
    ("todos", "Todos", "gray"), ("disponible", "Disponibles", "emerald"), ("prestado", "Prestados", "amber"),
    ("en_reparacion", "En reparación", "blue"), ("baja", "Baja", "gray"),
)


@login_required
@proteger_vista(APP_SLUG, "can_view_loans")
def bienes_view(request):
    abiertos = PrestamoBien.objects.filter(abierto=True).select_related("prestamo__documento")
    bienes = list(
        sel.bienes_visibles(request).select_related("categoria")
        .prefetch_related(Prefetch("asignaciones", queryset=abiertos, to_attr="abiertas"))
        .order_by("nombre", "identificador")
    )
    texto = request.GET.get("q", "").strip()[:100].casefold()
    if texto:
        bienes = [b for b in bienes if texto in f"{b.nombre} {b.identificador} {b.folio_inventario} {b.marca_modelo}".casefold()]
    categorias = list(CategoriaBien.objects.filter(pk__in={b.categoria_id for b in bienes if b.categoria_id}).order_by("nombre"))
    categoria = request.GET.get("categoria", "")
    if categoria == "sin":
        bienes = [b for b in bienes if not b.categoria_id]
    elif categoria in {str(c.pk) for c in categorias}:
        bienes = [b for b in bienes if str(b.categoria_id) == categoria]
    else:
        categoria = ""
    for bien in bienes:
        bien.situacion = "prestado" if bien.abiertas else bien.estado
        bien.prestamo_abierto = bien.abiertas[0].prestamo if bien.abiertas else None
    situacion = request.GET.get("situacion", "todos")
    if situacion not in {c for c, _, _ in SITUACIONES_BIEN}:
        situacion = "todos"
    conteos = {c: sum(1 for b in bienes if c == "todos" or b.situacion == c) for c, _, _ in SITUACIONES_BIEN}
    filas = [b for b in bienes if situacion == "todos" or b.situacion == situacion]
    pagina = Paginator(filas, 25).get_page(request.GET.get("pagina"))
    return _render(request, "bienes", {
        "pagina": pagina, "situacion": situacion, "texto": request.GET.get("q", ""), "total": len(filas),
        "categorias": categorias, "categoria": categoria,
        "tabs": [
            {"clave": c, "nombre": n, "color": col, "total": conteos[c], "activa": c == situacion, "query": _query(request, situacion=c)}
            for c, n, col in SITUACIONES_BIEN
        ],
        "query_sin_pagina": _query(request, situacion=situacion),
        "puede_gestionar": permitido(request, "can_manage_loans"),
    })


@login_required
@proteger_vista(APP_SLUG, "can_view_loans")
def bien_detalle_view(request, pk):
    bien = get_object_or_404(sel.bienes_visibles(request), pk=pk)
    asignaciones = list(
        bien.asignaciones.select_related("prestamo__documento", "prestamo__documento__gestor")
        .order_by("-prestamo__fecha_entrega")
    )
    actual = next((a.prestamo for a in asignaciones if a.abierto), None)
    return _render(request, "bien_detalle", {
        "bien": bien, "prestamo_actual": actual, "asignaciones": asignaciones,
        "historial": list(bien.historial.all())[::-1],
        "situacion": "prestado" if actual else bien.estado,
        "puede_gestionar": permitido(request, "can_manage_loans"),
    })


@login_required
@proteger_vista(APP_SLUG, "can_manage_loans")
def bien_form_view(request, pk=None):
    direcciones = sel.direcciones_con_vales(request, "can_manage_loans")
    bien = get_object_or_404(sel.bienes_visibles(request), pk=pk) if pk else None
    antes = foto_bien(bien) if bien else None
    form = BienForm(request.POST or None, instance=bien, direcciones=direcciones)
    if request.method == "POST" and form.is_valid():
        try:
            with transaction.atomic():
                guardado = form.save()
                if bien is None:
                    registrar_alta_bien(guardado, usuario=request.user)
                else:
                    registrar_cambios_bien(guardado, antes, usuario=request.user, motivo=form.cleaned_data.get("motivo", ""))
        except ValidationError as error:
            form.add_error(None, error)
        else:
            messages.success(request, f"Bien {guardado} guardado.")
            return redirect("seguimientos_oficios:bien_detalle", pk=guardado.pk)
    return _render(request, "bien_form", {"form": form, "bien": bien, "sin_habilitar": not direcciones.exists()})
