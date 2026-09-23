# core/views.py
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from apps.shared.module_sdk.launcher import build_launcher_context
from apps.shared.module_sdk.services import (
    module_center_cards,
    module_center_summary,
    public_directory_cards,
    set_module_enabled,
)
from apps.shared.utils.telemetry import AxentraRadar

User = get_user_model()


def index_hub_view(request):
    """Launcher administrativo dinámico y desacoplado de los satélites."""
    if not request.user.is_authenticated:
        return redirect("accounts:login")

    from apps.security.services.authority import is_platform_admin
    is_root = is_platform_admin(request.user)

    if AxentraRadar.enabled():
        AxentraRadar.imprimir_auditoria(
            componente="index_hub_view",
            request=request,
            titulo="Acceso al launcher de aplicaciones",
            icono="🏛️",
            extra_data={
                "Jurisdicción": "MASTER_BYPASS" if is_root else "OPERADOR_ESTÁNDAR",
                "Identidad": request.user.email,
            },
        )

    cards = module_center_cards(request.user)
    launcher_context = build_launcher_context(
        cards,
        is_root=is_root,
        query=request.GET.get("q", ""),
        state=request.GET.get("state", "all"),
        page=request.GET.get("page", 1),
    )
    context = {
        "is_root": is_root,
        "show_module_sidebar": False,
        "modulo_actual": "launcher",
        "module_summary": module_center_summary(cards),
        **launcher_context,
    }
    if request.headers.get("HX-Request") != "true":
        return render(request, "index_hub.html", context)

    # Igual que las vistas de Seguridad: el destino HTMX decide cuánto se reemplaza.
    # Sin esto, pedir el hub desde el nav móvil dejaba solo el buscador dentro de
    # #workbench, sin #page-content (scroll y padding) ni footer.
    target = request.headers.get("HX-Target", "")
    if target == "workbench":
        template = "launcher/_workbench.html"
    elif target == "page-content":
        template = "launcher/_page_content.html"
    else:
        template = "launcher/_content.html"
    return render(request, template, context)


@require_POST
def module_toggle_view(request, module_code):
    if not request.user.is_authenticated:
        return redirect("accounts:login")
    enabled = request.POST.get("enabled") == "1"
    try:
        module = set_module_enabled(
            code=module_code,
            enabled=enabled,
            actor=request.user,
            request=request,
        )
    except PermissionDenied:
        messages.error(request, "No tiene autorización para administrar módulos.")
    except (ValidationError, ValueError) as exc:
        messages.error(request, "; ".join(getattr(exc, "messages", [str(exc)])))
    else:
        action = "activado" if enabled else "desactivado"
        messages.success(request, f"El módulo {module.name} fue {action}.")
    return redirect("index_hub")


def intro_portal_view(request):
    """Renderiza la compuerta pública genérica de Axentra OS."""
    if request.user.is_authenticated:
        return redirect("index_hub")
    return render(request, "public/index.html")


def directorio_publico_view(request):
    """Directorio público (sin login) de servicios para el ciudadano.

    Complementa ``intro_portal_view``, que es la puerta de personal.
    """
    return render(request, "public/directorio.html", {
        "directorio_cards": public_directory_cards(),
    })
