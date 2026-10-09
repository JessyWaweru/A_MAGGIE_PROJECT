from django.db import transaction
from django.utils import timezone
from rest_framework import mixins, permissions, status, viewsets
from rest_framework.response import Response

from apps.accounts.emails import send_consultation_confirmed_emails

from .models import Consultation, Expert
from .serializers import BookConsultationSerializer, ConsultationSerializer, ExpertSerializer


class ExpertViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = ExpertSerializer
    permission_classes = [permissions.AllowAny]
    lookup_field = "slug"
    pagination_class = None

    def get_queryset(self):
        queryset = Expert.objects.filter(is_active=True)
        kind = self.request.query_params.get("kind")
        return queryset.filter(kind=kind) if kind else queryset


class ConsultationViewSet(
    mixins.CreateModelMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet
):
    """A customer's own bookings. Creating one returns it unpaid; payment goes through /payments/initialize/."""

    serializer_class = ConsultationSerializer
    permission_classes = [permissions.IsAuthenticated]
    lookup_field = "reference"

    def get_queryset(self):
        return Consultation.objects.filter(user=self.request.user).select_related("expert")

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        serializer = BookConsultationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        expert = data["expert_id"]
        consultation = Consultation.objects.create(
            user=request.user,
            expert=expert,
            mode=data["mode"],
            preferred_time=data["preferred_time"],
            phone_number=data["phone_number"],
            concern=data["concern"],
            consent_given_at=timezone.now(),
            fee=expert.fee,
            currency=expert.currency,
        )
        if not consultation.fee:
            # Free sessions skip Paystack, which can't charge zero.
            consultation.status = Consultation.Status.CONFIRMED
            consultation.save(update_fields=["status", "updated_at"])
            send_consultation_confirmed_emails(consultation)
        return Response(ConsultationSerializer(consultation).data, status=status.HTTP_201_CREATED)
