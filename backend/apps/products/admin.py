from django.contrib import admin

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


class ProductImageInline(admin.TabularInline):
    model = ProductImage
    extra = 1


class PlantGalleryImageInline(admin.TabularInline):
    model = PlantGalleryImage
    extra = 1


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ["name", "category", "price", "stock_quantity", "status", "is_featured", "is_bestseller", "average_rating"]
    list_filter = ["status", "is_featured", "is_bestseller", "category", "symptoms"]
    search_fields = ["name", "sku", "description"]
    prepopulated_fields = {"slug": ("name",)}
    filter_horizontal = ["symptoms", "ingredients"]
    readonly_fields = ["average_rating", "review_count", "sku"]
    inlines = [ProductImageInline, PlantGalleryImageInline]
    autocomplete_fields = ["category", "plant_origin"]


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ["name", "icon", "display_order"]
    prepopulated_fields = {"slug": ("name",)}
    search_fields = ["name"]


@admin.register(Symptom)
class SymptomAdmin(admin.ModelAdmin):
    list_display = ["name", "icon"]
    prepopulated_fields = {"slug": ("name",)}
    search_fields = ["name"]


@admin.register(Ingredient)
class IngredientAdmin(admin.ModelAdmin):
    list_display = ["name"]
    prepopulated_fields = {"slug": ("name",)}
    search_fields = ["name"]


@admin.register(PlantOrigin)
class PlantOriginAdmin(admin.ModelAdmin):
    list_display = ["name", "region", "country"]
    search_fields = ["name", "region", "country"]


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ["product", "user", "rating", "is_verified_purchase", "created_at"]
    list_filter = ["rating", "is_verified_purchase"]
    search_fields = ["product__name", "user__email"]


@admin.register(WishlistItem)
class WishlistItemAdmin(admin.ModelAdmin):
    list_display = ["user", "product", "created_at"]
