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
    template = (
        "launcher/_content.html"
        if request.headers.get("HX-Request") == "true"
        else "index_hub.html"
    )
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
