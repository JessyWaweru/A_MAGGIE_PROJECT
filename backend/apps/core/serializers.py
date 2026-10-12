from rest_framework import serializers

from apps.accounts.emails import send_newsletter_welcome_email
from apps.accounts.security import send_after_commit

from .models import ContactMessage, NewsletterSubscriber


class NewsletterSubscriberSerializer(serializers.ModelSerializer):
    class Meta:
        model = NewsletterSubscriber
        fields = ["email"]

    def create(self, validated_data):
        email = validated_data["email"]
        already_subscribed = NewsletterSubscriber.objects.filter(email=email, is_active=True).exists()
        subscriber, _ = NewsletterSubscriber.objects.update_or_create(email=email, defaults={"is_active": True})
        if not already_subscribed:
            send_after_commit(send_newsletter_welcome_email, email)
        return subscriber


class ContactMessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ContactMessage
        fields = ["id", "name", "email", "subject", "message", "created_at"]
        read_only_fields = ["id", "created_at"]
