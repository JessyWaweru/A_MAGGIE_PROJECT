from django.contrib import admin

from .models import Consultation, Expert


@admin.register(Expert)
class ExpertAdmin(admin.ModelAdmin):
    list_display = ["name", "kind", "title", "fee", "is_active", "sort_order"]
    list_editable = ["is_active", "sort_order"]
    list_filter = ["kind", "is_active"]
    search_fields = ["name", "title", "specialties"]
    prepopulated_fields = {"slug": ["name"]}


@admin.register(Consultation)
class ConsultationAdmin(admin.ModelAdmin):
    list_display = ["reference", "user", "expert", "mode", "status", "preferred_time", "scheduled_for"]
    list_filter = ["status", "mode", "expert"]
    search_fields = ["reference", "user__email", "phone_number"]
    readonly_fields = ["reference", "user", "expert", "fee", "currency", "paid_at", "consent_given_at", "concern"]
    fields = [
        "reference",
        "user",
        "expert",
        "status",
        "mode",
        "phone_number",
        "preferred_time",
        "scheduled_for",
        "meeting_link",
        "concern",
        "consent_given_at",
        "fee",
        "currency",
        "paid_at",
    ]
