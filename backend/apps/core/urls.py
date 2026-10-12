from django.urls import path

from .views import ContactMessageView, InboundEmailWebhookView, NewsletterSubscribeView, NewsletterUnsubscribeView

urlpatterns = [
    path("newsletter/subscribe/", NewsletterSubscribeView.as_view(), name="newsletter-subscribe"),
    path("newsletter/unsubscribe/", NewsletterUnsubscribeView.as_view(), name="newsletter-unsubscribe"),
    path("contact/", ContactMessageView.as_view(), name="contact-message"),
    path("webhooks/inbound-email/", InboundEmailWebhookView.as_view(), name="inbound-email-webhook"),
]
