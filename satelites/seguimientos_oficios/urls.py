from django.urls import path

from . import views

app_name = "seguimientos_oficios"

urlpatterns = [
    path("", views.documento_list_view, name="documento_list"),
    path("nuevo/", views.documento_create_view, name="documento_create"),
]
