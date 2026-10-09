from rest_framework.routers import DefaultRouter

from .views import ConsultationViewSet, ExpertViewSet

router = DefaultRouter()
router.register("experts", ExpertViewSet, basename="expert")
router.register("bookings", ConsultationViewSet, basename="consultation")

urlpatterns = router.urls
