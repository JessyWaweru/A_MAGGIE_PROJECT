from django.urls import path

from .views import ContactMessageView, NewsletterSubscribeView

urlpatterns = [
    path("newsletter/subscribe/", NewsletterSubscribeView.as_view(), name="newsletter-subscribe"),
    path("contact/", ContactMessageView.as_view(), name="contact-message"),
]
