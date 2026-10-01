from rest_framework.routers import DefaultRouter

from .views import PayoutViewSet

router = DefaultRouter()
router.register("", PayoutViewSet, basename="payout")
urlpatterns = router.urls
