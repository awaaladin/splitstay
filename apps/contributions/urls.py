from rest_framework.routers import DefaultRouter

from .views import ContributionViewSet

router = DefaultRouter()
router.register("", ContributionViewSet, basename="contribution")
urlpatterns = router.urls
