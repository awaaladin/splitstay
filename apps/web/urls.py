from django.urls import path

from . import views

app_name = "web"

urlpatterns = [
    path("", views.landing, name="landing"),
    path("guide/", views.guide, name="guide"),
    path("about/", views.about, name="about"),
    path("fees/", views.pricing, name="pricing"),
    path("contact/", views.contact, name="contact"),
    path("privacy/", views.privacy, name="privacy"),
    path("terms/", views.terms, name="terms"),
    path("login/", views.login_view, name="login"),
    path("register/", views.register, name="register"),
    path("logout/", views.logout_view, name="logout"),
    path("dashboard/", views.dashboard, name="dashboard"),
    path("groups/new/", views.group_new, name="group_new"),
    path("groups/<int:pk>/", views.group_detail, name="group_detail"),
    path("groups/<int:pk>/edit/", views.group_edit, name="group_edit"),
    path("groups/<int:pk>/live/", views.group_live, name="group_live"),
    path("groups/<int:pk>/ledger/", views.group_ledger, name="group_ledger"),
    path("groups/<int:pk>/receipt/", views.group_receipt, name="group_receipt"),
    path("groups/<int:pk>/invite/", views.group_invite, name="group_invite"),
    path("groups/<int:pk>/members/<int:user_id>/remove/", views.group_member_remove, name="group_member_remove"),
    path("groups/<int:pk>/members/<int:user_id>/share/", views.group_member_share, name="group_member_share"),
    path("groups/<int:pk>/accept/", views.group_accept, name="group_accept"),
    path("groups/<int:pk>/decline/", views.group_decline, name="group_decline"),
    path("groups/<int:pk>/cancel/", views.group_cancel, name="group_cancel"),
    path("groups/<int:pk>/payout/", views.group_payout, name="group_payout"),
    path("groups/<int:pk>/pay/", views.group_pay, name="group_pay"),
    path("pay/return/", views.payment_return, name="payment_return"),
    path("pay/mock/<str:reference>/", views.mock_checkout, name="mock_checkout"),
    path("contributions/<str:reference>/confirmation/", views.contribution_confirmation, name="contribution_confirmation"),
    path("notifications/", views.notifications, name="notifications"),
    path("notifications/bell/", views.notifications_bell, name="notifications_bell"),
    path("notifications/read-all/", views.notifications_read_all, name="notifications_read_all"),
    path("notifications/<int:pk>/open/", views.notification_open, name="notification_open"),
    path("settings/", views.account_settings, name="settings"),
    path("billers/validate/", views.validate_meter, name="validate_meter"),
]
