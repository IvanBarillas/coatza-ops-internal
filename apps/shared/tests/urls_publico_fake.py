from django.http import HttpResponse
from django.urls import path

app_name = "portal_falso"
urlpatterns = [path("hola/", lambda request: HttpResponse("hola-publico"), name="hola")]
