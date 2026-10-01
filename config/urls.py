from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

api_v1 = [
    path("auth/", include("apps.accounts.urls")),
    path("groups/", include("apps.groups.urls")),
    path("contributions/", include("apps.contributions.urls")),
    path("payments/", include("apps.payments.urls")),
    path("billpay/", include("apps.billpay.urls")),
    path("payouts/", include("apps.payouts.urls")),
    path("notifications/", include("apps.notifications.urls")),
    path("ledger/", include("apps.ledger.urls")),
]

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/v1/", include((api_v1, "api"), namespace="v1")),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="docs"),
    path("", include("config.cron")),
    path("", include("apps.web.urls")),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
