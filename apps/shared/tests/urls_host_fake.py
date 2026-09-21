"""Urlconfs mínimos para probar el enrutamiento por host y las APIs de satélites."""
from django.http import HttpResponse
from django.urls import path

urlpatterns = [path("", lambda request: HttpResponse("superficie-publica"), name="publica")]
