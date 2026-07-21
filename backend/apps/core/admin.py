from django.contrib import admin

from .models import ContactMessage, NewsletterSubscriber


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
