from django.urls import path
from query.views import HealthView, QueryView, StatsView

urlpatterns = [
    path("health/", HealthView.as_view(), name="api-health"),
    path("query/", QueryView.as_view(), name="api-query"),
    path("stats/", StatsView.as_view(), name="api-stats"),
]
