from django.urls import path

from . import views

urlpatterns = [
    path("me/", views.MyLedgerView.as_view(), name="my-ledger"),
    path("groups/<int:group_id>/", views.GroupLedgerView.as_view(), name="group-ledger"),
]
