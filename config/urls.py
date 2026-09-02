from django.contrib import admin
from django.urls import path, include

from query.views import RootView, FrontendView

urlpatterns = [
    path("", FrontendView.as_view(), name="frontend"),  # Serve frontend at root
    path("admin/", admin.site.urls),
    path("api/", include("query.urls")),
]
