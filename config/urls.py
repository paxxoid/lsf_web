from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path



from wagtail.admin import urls as wagtailadmin_urls
from wagtail.documents import urls as wagtaildocs_urls



from guild import views
from guild.api import api

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/", include("django.contrib.auth.urls")),
    path("api/", api.urls),

    # Wagtail CMS
    path("cms/", include(wagtailadmin_urls)),

    # Wagtail document delivery
    path("documents/", include(wagtaildocs_urls)),    

 

    path("", include("guild.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
