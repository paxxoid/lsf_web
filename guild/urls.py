from django.urls import path

from . import views

app_name = "guild"

urlpatterns = [
    path("", views.home, name="home"),
    path("about/", views.about, name="about"),
    path("roster/", views.roster, name="roster"),
    path("raids/", views.raids, name="raids"),
    path("attendance/", views.attendance, name="attendance"),
    path("loot/", views.loot, name="loot"),
    path("screenshots/", views.screenshots, name="screenshots"),
    #path("news/", views.news, name="news"),
    path("apply/", views.apply, name="apply"),
    path("apply/success/", views.application_success, name="application_success"),
    path(
        "news/",
        views.news,
        name="news",
    ),

    path(
        "news/<slug:slug>/",
        views.news_detail,
        name="news_detail",
    ),    
]
