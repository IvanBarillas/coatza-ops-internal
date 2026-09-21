from django.http import JsonResponse
from django.urls import path

app_name = "fake_api"
urlpatterns = [path("ping", lambda request: JsonResponse({"ok": True}), name="ping")]
