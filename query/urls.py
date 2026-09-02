from django.urls import path
from query.views import (
    RootView,
    HealthView,
    QueryView,
    StatsView,
    UploadDocumentsView,
    DocumentStatsView,
)

urlpatterns = [
    path("", RootView.as_view(), name="api-root"),
    path("health/", HealthView.as_view(), name="api-health"),
    path("query/", QueryView.as_view(), name="api-query"),
    path("stats/", StatsView.as_view(), name="api-stats"),
    path("upload/", UploadDocumentsView.as_view(), name="api-upload"),
    path("document-stats/", DocumentStatsView.as_view(), name="api-document-stats"),
]
