from django.contrib import admin
from django.urls import path, include, re_path
from django.conf import settings
from django.views.static import serve

from query.views import RootView, FrontendView

urlpatterns = [
    path("", FrontendView.as_view(), name="frontend"),  # Serve frontend at root
    path("admin/", admin.site.urls),
    path("api/", include("query.urls")),
    re_path(r"^media/(?P<path>.*)$", serve, {"document_root": settings.MEDIA_ROOT}),
]

