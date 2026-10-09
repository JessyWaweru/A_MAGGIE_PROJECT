from datetime import timedelta

from django.utils import timezone
from rest_framework import serializers

from .models import Consultation, Expert, Mode


class ExpertSerializer(serializers.ModelSerializer):
    kind_label = serializers.CharField(source="get_kind_display", read_only=True)
    modes = serializers.ListField(child=serializers.CharField(), read_only=True)

    class Meta:
        model = Expert
        fields = [
            "id",
            "slug",
            "name",
            "kind",
            "kind_label",
            "title",
            "photo_url",
            "bio",
            "specialties",
            "languages",
            "licence_number",
            "fee",
            "currency",
            "session_minutes",
            "modes",
        ]


class ConsultationSerializer(serializers.ModelSerializer):
    expert = ExpertSerializer(read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = Consultation
        fields = [
            "id",
            "reference",
            "expert",
            "status",
            "status_label",
            "mode",
            "preferred_time",
            "scheduled_for",
            "meeting_link",
            "phone_number",
            "concern",
            "fee",
            "currency",
            "paid_at",
            "created_at",
        ]
        read_only_fields = fields


class BookConsultationSerializer(serializers.Serializer):
    expert_id = serializers.PrimaryKeyRelatedField(queryset=Expert.objects.filter(is_active=True))
    mode = serializers.ChoiceField(choices=Mode.choices)
    preferred_time = serializers.DateTimeField()
    phone_number = serializers.CharField(min_length=7, max_length=20)
    concern = serializers.CharField(min_length=10, max_length=4000)
    consent = serializers.BooleanField()

    def validate_preferred_time(self, value):
        if value < timezone.now() + timedelta(hours=1):
            raise serializers.ValidationError("Pick a time at least an hour from now.")
        return value

    def validate_consent(self, value):
        if not value:
            raise serializers.ValidationError("We need your consent to share your health details with the expert.")
        return value

    def validate(self, attrs):
        if attrs["mode"] not in attrs["expert_id"].modes:
            raise serializers.ValidationError({"mode": "This expert doesn't offer that type of session."})
        return attrs
