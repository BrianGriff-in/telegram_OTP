from django.urls import path

from . import views

urlpatterns = [
    path("signup/", views.signup_view, name="signup"),
    path("login/", views.login_view, name="login"),
    path("verify-otp/", views.verify_otp_view, name="verify_otp"),
    path("resend-otp/", views.resend_otp_view, name="resend_otp"),
    path("logout/", views.logout_view, name="logout"),
    path("link-telegram/", views.link_telegram_view, name="link_telegram"),
    path("link-telegram/status/", views.link_telegram_status_view, name="link_telegram_status"),
    path("dashboard/", views.dashboard_view, name="dashboard"),
    path(
        "telegram/webhook/<str:secret>/",
        views.telegram_webhook_view,
        name="telegram_webhook",
    ),
]
