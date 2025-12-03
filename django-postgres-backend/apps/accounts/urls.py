
from django.urls import path

from .views import (
    UsersListCreateView,
         # <-- import the new view
    ForgotPasswordView,
    VerifyOTPView,
    ResetPasswordView,
    LogoutView,
    HealthView,
)

urlpatterns = [
    path("", HealthView.as_view()),
    path("users/", UsersListCreateView.as_view()),          # list + create
     # detail: get, delete
    path("forgot-password/", ForgotPasswordView.as_view()),
    path("verify-otp/", VerifyOTPView.as_view()),
    path("reset-password/", ResetPasswordView.as_view()),
    path("logout/", LogoutView.as_view()),
]
