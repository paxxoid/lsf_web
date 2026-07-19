from django.urls import path

from . import views

app_name = "guild"

urlpatterns = [
    path("", views.home, name="home"),
]