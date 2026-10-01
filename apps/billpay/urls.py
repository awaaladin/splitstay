from django.urls import path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("payments", views.BillPaymentViewSet, basename="bill-payment")

urlpatterns = [
    path("billers/", views.BillerListView.as_view(), name="billers"),
    path("validate/", views.ValidateMeterView.as_view(), name="validate-meter"),
] + router.urls
