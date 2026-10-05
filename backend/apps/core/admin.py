from django.contrib import admin

from .models import ContactMessage, InboundEmail, NewsletterSubscriber


@admin.register(NewsletterSubscriber)
class NewsletterSubscriberAdmin(admin.ModelAdmin):
    list_display = ["email", "is_active", "created_at"]
    list_filter = ["is_active"]
    search_fields = ["email"]


@admin.register(ContactMessage)
class ContactMessageAdmin(admin.ModelAdmin):
    list_display = ["name", "email", "subject", "is_resolved", "created_at"]
    list_filter = ["is_resolved"]
    search_fields = ["name", "email", "subject", "message"]


@admin.register(InboundEmail)
class InboundEmailAdmin(admin.ModelAdmin):
    list_display = ["from_address", "to_address", "subject", "is_read", "created_at"]
    list_filter = ["is_read"]
    search_fields = ["from_address", "to_address", "subject", "text_body"]
    readonly_fields = ["message_id", "from_address", "to_address", "subject", "text_body", "html_body", "raw_payload", "created_at"]
