import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models

from apps.core.models import TimeStampedModel


def generate_consultation_reference():
    return f"CN-{uuid.uuid4().hex[:10].upper()}"


class Mode(models.TextChoices):
    WHATSAPP = "whatsapp", "WhatsApp chat"
    PHONE = "phone", "Phone call"
    VIDEO = "video", "Video call"


class Expert(TimeStampedModel):
    """A herbal coach or medical specialist customers can book a paid consultation with."""

    class Kind(models.TextChoices):
        HERBAL_COACH = "herbal_coach", "Herbal coach"
        MEDICAL_SPECIALIST = "medical_specialist", "Medical specialist"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    slug = models.SlugField(unique=True)
    name = models.CharField(max_length=150)
    kind = models.CharField(max_length=20, choices=Kind.choices)
    title = models.CharField(max_length=150, help_text="e.g. 'Clinical Herbalist' or 'General Practitioner'")
    photo_url = models.URLField(blank=True, help_text="Public https link to a square photo.")
    bio = models.TextField()
    specialties = models.CharField(max_length=255, blank=True, help_text="Comma-separated, e.g. 'Digestion, Sleep'")
    languages = models.CharField(max_length=100, default="English, Swahili")
    licence_number = models.CharField(
        max_length=50, blank=True, help_text="Required for medical specialists (KMPDC registration number)."
    )
    fee = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)])
    currency = models.CharField(max_length=3, default="KES")
    session_minutes = models.PositiveIntegerField(default=30)
    offers_whatsapp = models.BooleanField(default=True)
    offers_phone = models.BooleanField(default=True)
    offers_video = models.BooleanField(default=False)
    email = models.EmailField(blank=True, help_text="Private. New paid bookings are emailed here.")
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "name"]

    def __str__(self):
        return f"{self.name} ({self.get_kind_display()})"

    def clean(self):
        if self.kind == self.Kind.MEDICAL_SPECIALIST and not self.licence_number.strip():
            raise ValidationError({"licence_number": "Medical specialists must have a licence number."})
        if not self.modes:
            raise ValidationError("Offer at least one way to consult (WhatsApp, phone or video).")

    @property
    def modes(self):
        offered = [(Mode.WHATSAPP, self.offers_whatsapp), (Mode.PHONE, self.offers_phone), (Mode.VIDEO, self.offers_video)]
        return [mode.value for mode, on in offered if on]


class Consultation(TimeStampedModel):
    """A booked session. Confirmed once paid; the team then fixes the exact time with the customer."""

    class Status(models.TextChoices):
        PENDING_PAYMENT = "pending_payment", "Pending payment"
        CONFIRMED = "confirmed", "Paid — awaiting scheduling"
        SCHEDULED = "scheduled", "Scheduled"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"
        REFUNDED = "refunded", "Refunded"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    reference = models.CharField(
        max_length=20, unique=True, default=generate_consultation_reference, editable=False
    )
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="consultations")
    expert = models.ForeignKey(Expert, on_delete=models.PROTECT, related_name="consultations")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING_PAYMENT)
    mode = models.CharField(max_length=10, choices=Mode.choices)
    preferred_time = models.DateTimeField()
    phone_number = models.CharField(max_length=20)
    # Health information is sensitive personal data (Kenya Data Protection Act, 2019): collected
    # only with explicit consent and shown only to the customer, the assigned expert and admins.
    concern = models.TextField()
    consent_given_at = models.DateTimeField()
    fee = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, default="KES")
    paid_at = models.DateTimeField(null=True, blank=True)
    scheduled_for = models.DateTimeField(null=True, blank=True, help_text="The confirmed session time.")
    meeting_link = models.URLField(blank=True, help_text="Video calls: the link the customer should join.")

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.reference} with {self.expert.name}"
