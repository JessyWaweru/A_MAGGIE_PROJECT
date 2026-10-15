from rest_framework import serializers

from apps.accounts.emails import send_newsletter_welcome_email
from apps.accounts.security import send_after_commit

from .forwarding import forward_contact_message
from .models import ContactMessage, NewsletterSubscriber


class NewsletterSubscriberSerializer(serializers.ModelSerializer):
    # Plain field so an address already on the list re-subscribes instead of failing the unique check.
    email = serializers.EmailField()

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
        extra_kwargs = {"message": {"max_length": 5000}}

    def create(self, validated_data):
        contact = super().create(validated_data)
        send_after_commit(forward_contact_message, contact)
        return contact
