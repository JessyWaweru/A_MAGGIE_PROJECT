from django.urls import path

from .views import InitializePaymentView, PaystackWebhookView, VerifyPaymentView

urlpatterns = [
    path("initialize/", InitializePaymentView.as_view(), name="payment-initialize"),
    path("verify/<str:reference>/", VerifyPaymentView.as_view(), name="payment-verify"),
    path("webhook/paystack/", PaystackWebhookView.as_view(), name="payment-webhook-paystack"),
]
