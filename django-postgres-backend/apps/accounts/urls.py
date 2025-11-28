from django.urls import path

from .views import ForgotPasswordView, HealthView, LogoutView, ResetPasswordView, VerifyOtpView

urlpatterns = [
    path('', HealthView.as_view(), name='accounts-root'),
    path('forgot-password/', ForgotPasswordView.as_view(), name='accounts-forgot-password'),
    path('reset-password/', ResetPasswordView.as_view(), name='accounts-reset-password'),
    path('verify-otp/', VerifyOtpView.as_view(), name='accounts-verify-otp'),
    path('logout/', LogoutView.as_view(), name='accounts-logout'),
]

