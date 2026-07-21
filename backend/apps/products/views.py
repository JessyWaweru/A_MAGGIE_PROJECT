from django.shortcuts import get_object_or_404
from rest_framework import generics, permissions, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from .filters import ProductFilter
from .models import Category, Ingredient, PlantOrigin, Product, Review, Symptom, WishlistItem
from .serializers import (
    CategorySerializer,
    IngredientSerializer,
    PlantOriginSerializer,
    ProductDetailSerializer,
    ProductListSerializer,
    ReviewCreateSerializer,
    ReviewSerializer,
    SymptomSerializer,
    WishlistItemSerializer,
)

PRODUCT_RELATED = ("category", "plant_origin")
PRODUCT_PREFETCH = ("symptoms", "ingredients", "gallery_images", "plant_gallery_images", "reviews__user")


class ProductViewSet(viewsets.ReadOnlyModelViewSet):
    """Browse & search products - by free-text query or by symptom/category/ingredient facets."""

    lookup_field = "slug"
    filterset_class = ProductFilter
    search_fields = [
        "name",
        "short_description",
        "description",
        "how_it_helps",
        "ingredients__name",
        "symptoms__name",
        "category__name",
    ]
    ordering_fields = ["price", "created_at", "average_rating", "name"]
    permission_classes = [permissions.AllowAny]

    def get_queryset(self):
        qs = Product.objects.filter(status=Product.Status.ACTIVE).select_related(*PRODUCT_RELATED)
        if self.action == "retrieve":
            qs = qs.prefetch_related(*PRODUCT_PREFETCH)
        else:
            qs = qs.prefetch_related("symptoms")
        return qs.distinct()

    def get_serializer_class(self):
        if self.action == "retrieve":
            return ProductDetailSerializer
        return ProductListSerializer

    @action(detail=False, methods=["get"])
    def featured(self, request):
        qs = self.filter_queryset(self.get_queryset().filter(is_featured=True))
        page = self.paginate_queryset(qs)
        serializer = self.get_serializer(page or qs, many=True)
        return self.get_paginated_response(serializer.data) if page is not None else Response(serializer.data)

    @action(detail=False, methods=["get"])
    def bestsellers(self, request):
        qs = self.filter_queryset(self.get_queryset().filter(is_bestseller=True))
        page = self.paginate_queryset(qs)
        serializer = self.get_serializer(page or qs, many=True)
        return self.get_paginated_response(serializer.data) if page is not None else Response(serializer.data)


class CategoryViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer
    lookup_field = "slug"
    permission_classes = [permissions.AllowAny]
    pagination_class = None


class SymptomViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Symptom.objects.all()
    serializer_class = SymptomSerializer
    lookup_field = "slug"
    permission_classes = [permissions.AllowAny]
    pagination_class = None


class IngredientViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Ingredient.objects.all()
    serializer_class = IngredientSerializer
    lookup_field = "slug"
    permission_classes = [permissions.AllowAny]
    pagination_class = None


class PlantOriginViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = PlantOrigin.objects.all()
    serializer_class = PlantOriginSerializer
    permission_classes = [permissions.AllowAny]
    pagination_class = None


class ProductReviewListCreateView(generics.ListCreateAPIView):
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]

    def get_product(self):
        return get_object_or_404(Product, slug=self.kwargs["product_slug"])

    def get_queryset(self):
        return Review.objects.filter(product=self.get_product()).select_related("user")

    def get_serializer_class(self):
        return ReviewCreateSerializer if self.request.method == "POST" else ReviewSerializer

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["product"] = self.get_product()
        return context

    def perform_create(self, serializer):
        serializer.save()


class WishlistViewSet(viewsets.ModelViewSet):
    serializer_class = WishlistItemSerializer
    permission_classes = [permissions.IsAuthenticated]
    http_method_names = ["get", "post", "delete", "head", "options"]

    def get_queryset(self):
        return WishlistItem.objects.filter(user=self.request.user).select_related("product", "product__category")

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)
