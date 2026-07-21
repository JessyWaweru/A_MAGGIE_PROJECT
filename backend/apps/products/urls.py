from rest_framework.routers import DefaultRouter

from django.urls import include, path

from .views import (
    CategoryViewSet,
    IngredientViewSet,
    PlantOriginViewSet,
    ProductReviewListCreateView,
    ProductViewSet,
    SymptomViewSet,
    WishlistViewSet,
)

router = DefaultRouter()
router.register("products", ProductViewSet, basename="product")
router.register("categories", CategoryViewSet, basename="category")
router.register("symptoms", SymptomViewSet, basename="symptom")
router.register("ingredients", IngredientViewSet, basename="ingredient")
router.register("plant-origins", PlantOriginViewSet, basename="plant-origin")
router.register("wishlist", WishlistViewSet, basename="wishlist")

urlpatterns = [
    path("products/<slug:product_slug>/reviews/", ProductReviewListCreateView.as_view(), name="product-reviews"),
    path("", include(router.urls)),
]
