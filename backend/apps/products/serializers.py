from rest_framework import serializers

from .models import (
    Category,
    Ingredient,
    PlantGalleryImage,
    PlantOrigin,
    Product,
    ProductImage,
    Review,
    Symptom,
    WishlistItem,
)


class CategorySerializer(serializers.ModelSerializer):
    image_url = serializers.ReadOnlyField()
    product_count = serializers.IntegerField(source="products.count", read_only=True)

    class Meta:
        model = Category
        fields = ["id", "name", "slug", "description", "icon", "image_url", "product_count", "display_order"]


class SymptomSerializer(serializers.ModelSerializer):
    product_count = serializers.IntegerField(source="products.count", read_only=True)

    class Meta:
        model = Symptom
        fields = ["id", "name", "slug", "description", "icon", "product_count"]


class IngredientSerializer(serializers.ModelSerializer):
    class Meta:
        model = Ingredient
        fields = ["id", "name", "slug", "description"]


class PlantOriginSerializer(serializers.ModelSerializer):
    class Meta:
        model = PlantOrigin
        fields = ["id", "name", "region", "country", "description", "latitude", "longitude"]


class ProductImageSerializer(serializers.ModelSerializer):
    image_url = serializers.ReadOnlyField()

    class Meta:
        model = ProductImage
        fields = ["id", "image_url", "alt_text", "display_order"]


class PlantGalleryImageSerializer(serializers.ModelSerializer):
    image_url = serializers.ReadOnlyField()

    class Meta:
        model = PlantGalleryImage
        fields = ["id", "image_url", "caption", "display_order"]


class ReviewSerializer(serializers.ModelSerializer):
    user_name = serializers.SerializerMethodField()

    class Meta:
        model = Review
        fields = [
            "id",
            "user_name",
            "rating",
            "title",
            "comment",
            "is_verified_purchase",
            "created_at",
        ]
        read_only_fields = ["id", "is_verified_purchase", "created_at"]

    def get_user_name(self, obj):
        full_name = f"{obj.user.first_name} {obj.user.last_name}".strip()
        return full_name or obj.user.email.split("@")[0]


class ReviewCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Review
        fields = ["rating", "title", "comment"]

    def validate(self, attrs):
        request = self.context["request"]
        product = self.context["product"]
        if Review.objects.filter(product=product, user=request.user).exists():
            raise serializers.ValidationError("You've already reviewed this product.")
        return attrs

    def create(self, validated_data):
        request = self.context["request"]
        product = self.context["product"]
        from apps.orders.models import OrderItem

        is_verified_purchase = OrderItem.objects.filter(
            order__user=request.user,
            product=product,
            order__status="paid",
        ).exists()
        return Review.objects.create(
            product=product,
            user=request.user,
            is_verified_purchase=is_verified_purchase,
            **validated_data,
        )


class ProductListSerializer(serializers.ModelSerializer):
    """Lightweight representation for grids/search results."""

    primary_image_url = serializers.ReadOnlyField()
    category = CategorySerializer(read_only=True)
    symptoms = SymptomSerializer(many=True, read_only=True)
    is_in_stock = serializers.ReadOnlyField()

    class Meta:
        model = Product
        fields = [
            "id",
            "name",
            "slug",
            "short_description",
            "price",
            "compare_at_price",
            "currency",
            "primary_image_url",
            "category",
            "symptoms",
            "is_in_stock",
            "is_featured",
            "is_bestseller",
            "average_rating",
            "review_count",
        ]


class ProductDetailSerializer(serializers.ModelSerializer):
    primary_image_url = serializers.ReadOnlyField()
    category = CategorySerializer(read_only=True)
    symptoms = SymptomSerializer(many=True, read_only=True)
    ingredients = IngredientSerializer(many=True, read_only=True)
    plant_origin = PlantOriginSerializer(read_only=True)
    gallery_images = ProductImageSerializer(many=True, read_only=True)
    plant_gallery_images = PlantGalleryImageSerializer(many=True, read_only=True)
    reviews = ReviewSerializer(many=True, read_only=True)
    is_in_stock = serializers.ReadOnlyField()
    related_products = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = [
            "id",
            "name",
            "slug",
            "sku",
            "short_description",
            "description",
            "how_it_helps",
            "usage_instructions",
            "price",
            "compare_at_price",
            "currency",
            "stock_quantity",
            "is_in_stock",
            "primary_image_url",
            "category",
            "symptoms",
            "ingredients",
            "plant_origin",
            "gallery_images",
            "plant_gallery_images",
            "reviews",
            "is_featured",
            "is_bestseller",
            "average_rating",
            "review_count",
            "related_products",
        ]

    def get_related_products(self, obj):
        related = (
            Product.objects.filter(symptoms__in=obj.symptoms.all(), status=Product.Status.ACTIVE)
            .exclude(pk=obj.pk)
            .distinct()[:4]
        )
        return ProductListSerializer(related, many=True, context=self.context).data


class WishlistItemSerializer(serializers.ModelSerializer):
    product = ProductListSerializer(read_only=True)
    product_id = serializers.PrimaryKeyRelatedField(
        source="product", queryset=Product.objects.all(), write_only=True
    )

    class Meta:
        model = WishlistItem
        fields = ["id", "product", "product_id", "created_at"]
        read_only_fields = ["id", "created_at"]
