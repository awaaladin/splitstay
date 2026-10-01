from django.urls import path

from . import views

urlpatterns = [
    path("webhooks/paystack/", views.PaystackWebhookView.as_view(), name="webhook-paystack"),
    path("verify/<str:reference>/", views.VerifyPaymentView.as_view(), name="verify"),
]
