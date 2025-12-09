
from django.urls import path

from .views import (
    UsersListCreateView,
    CurrentUserView,  # <-- import the new view
    ForgotPasswordView,
    VerifyOTPView,
    ResetPasswordView,
    LogoutView,
    HealthView,
)

urlpatterns = [
    path("", HealthView.as_view()),
    path("users/", UsersListCreateView.as_view()),          # list + create
    path("users/me/", CurrentUserView.as_view()),  
    path("forgot-password/", ForgotPasswordView.as_view()),
    path("verify-otp/", VerifyOTPView.as_view()),
    path("reset-password/", ResetPasswordView.as_view()),
    path("logout/", LogoutView.as_view()),
]
