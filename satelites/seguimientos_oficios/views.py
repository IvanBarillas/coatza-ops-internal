from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from .forms import DocumentoForm
from .integracion import proteger_vista
from .selectors import APP_SLUG, direcciones_visibles, documentos_visibles


def _render(request, nombre, contexto):
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
        documento = form.save(commit=False)
        documento.creado_por = request.user
        documento.save()
        messages.success(request, "Oficio registrado.")
        return redirect("seguimientos_oficios:documento_list")
    return _render(request, "documento_form", {"form": form})
