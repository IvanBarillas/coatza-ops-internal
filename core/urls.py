# core/urls.py
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from core.views import module_toggle_view
from core.views import directorio_publico_view, intro_portal_view, index_hub_view
from apps.shared.module_sdk.routing import satellite_urlpatterns

urlpatterns = [
    # ──► 1. Panel de Administración Ofuscado
    path(settings.ADMIN_SECRET_PATH, admin.site.urls),

    # ──► 2. Compuerta Externa de Bienvenida (La raíz real de Axentra OS)
    path('', intro_portal_view, name='intro_portal'),

    # ──► 2b. Directorio público de servicios para el ciudadano (sin login)
    path('directorio/', directorio_publico_view, name='directorio_publico'),

    # ──► 3. Selector Autónomo de Aplicaciones (El Launcher)
    path('index/', index_hub_view, name='index_hub'),
    
    path("modules/<slug:module_code>/toggle/", module_toggle_view, name="module_toggle",),

    path('app/', include('apps.security.urls')),

    # Satélites instalados mediante su module_manifest.py
    *satellite_urlpatterns(),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)