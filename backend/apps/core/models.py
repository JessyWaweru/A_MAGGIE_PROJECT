import uuid

from django.db import models


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class NewsletterSubscriber(TimeStampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.email


class ContactMessage(TimeStampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=150)
    email = models.EmailField()
    subject = models.CharField(max_length=200, blank=True)
    message = models.TextField()
    is_resolved = models.BooleanField(default=False)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.name} <{self.email}>: {self.subject or self.message[:30]}"


class InboundEmail(TimeStampedModel):
    """An email received at an @goherbal.health address, via Resend's inbound webhook."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    message_id = models.CharField(max_length=255, blank=True, db_index=True)
    from_address = models.EmailField(blank=True)
    to_address = models.EmailField(blank=True)
    subject = models.CharField(max_length=500, blank=True)
    text_body = models.TextField(blank=True)
    html_body = models.TextField(blank=True)
    # The full, unmodified webhook payload - a safety net in case Resend's exact
    # field names differ from what we extract above, so no data is ever lost.
    raw_payload = models.JSONField(default=dict)
    is_read = models.BooleanField(default=False)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"From {self.from_address or 'unknown'}: {self.subject or '(no subject)'}"
