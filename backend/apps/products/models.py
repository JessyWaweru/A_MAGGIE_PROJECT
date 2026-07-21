import uuid

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from apps.core.models import TimeStampedModel
from apps.core.utils import unique_slugify

PLACEHOLDER_PRODUCT_IMAGE = "placeholders/product-placeholder.svg"
PLACEHOLDER_GARDEN_IMAGE = "placeholders/garden-placeholder.svg"
PLACEHOLDER_CATEGORY_IMAGE = "placeholders/category-placeholder.svg"


class Category(TimeStampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=120, unique=True)
    slug = models.SlugField(max_length=140, unique=True, blank=True)
    description = models.TextField(blank=True)
    icon = models.CharField(max_length=8, blank=True, help_text="A single emoji, e.g. 🌿")
    image = models.ImageField(upload_to="categories/", blank=True, null=True)
    display_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["display_order", "name"]
        verbose_name_plural = "categories"

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = unique_slugify(self, self.name)
        super().save(*args, **kwargs)

    @property
    def image_url(self):
        if self.image:
            return self.image.url
        return f"{settings.STATIC_URL}{PLACEHOLDER_CATEGORY_IMAGE}"


class Symptom(TimeStampedModel):
    """An ailment / concern a shopper is trying to resolve, e.g. Headache, Insomnia."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=120, unique=True)
    slug = models.SlugField(max_length=140, unique=True, blank=True)
    description = models.TextField(blank=True)
    icon = models.CharField(max_length=8, blank=True, help_text="A single emoji, e.g. 🤕")

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = unique_slugify(self, self.name)
        super().save(*args, **kwargs)


class Ingredient(TimeStampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=120, unique=True)
    slug = models.SlugField(max_length=140, unique=True, blank=True)
    description = models.TextField(blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = unique_slugify(self, self.name)
        super().save(*args, **kwargs)


class PlantOrigin(TimeStampedModel):
    """Where the source plant is grown/harvested — used for the 'from the garden' story."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=150, help_text="e.g. Meru Highlands Herb Garden")
    region = models.CharField(max_length=150, blank=True)
    country = models.CharField(max_length=100, default="Kenya")
    description = models.TextField(blank=True, help_text="Growing conditions, harvest story, etc.")
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.country})"


class Product(TimeStampedModel):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        ACTIVE = "active", "Active"
        ARCHIVED = "archived", "Archived"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=220, unique=True, blank=True)
    sku = models.CharField(max_length=64, unique=True, blank=True)

    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, blank=True, related_name="products")
    symptoms = models.ManyToManyField(Symptom, blank=True, related_name="products")
    ingredients = models.ManyToManyField(Ingredient, blank=True, related_name="products")
    plant_origin = models.ForeignKey(
        PlantOrigin, on_delete=models.SET_NULL, null=True, blank=True, related_name="products"
    )

    short_description = models.CharField(max_length=300, blank=True)
    description = models.TextField(blank=True)
    how_it_helps = models.TextField(blank=True, help_text="What this remedy helps with, in plain language.")
    usage_instructions = models.TextField(blank=True)

    price = models.DecimalField(max_digits=10, decimal_places=2)
    compare_at_price = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True, help_text="Optional 'was' price for showing a discount."
    )
    currency = models.CharField(max_length=3, default="KES")

    stock_quantity = models.PositiveIntegerField(default=0)
    primary_image = models.ImageField(upload_to="products/", blank=True, null=True)

    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ACTIVE)
    is_featured = models.BooleanField(default=False)
    is_bestseller = models.BooleanField(default=False)

    average_rating = models.DecimalField(max_digits=3, decimal_places=2, default=0)
    review_count = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "is_featured"]),
            models.Index(fields=["status", "is_bestseller"]),
        ]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = unique_slugify(self, self.name)
        if not self.sku:
            self.sku = f"HR-{uuid.uuid4().hex[:8].upper()}"
        super().save(*args, **kwargs)

    @property
    def is_in_stock(self):
        return self.stock_quantity > 0

    @property
    def primary_image_url(self):
        if self.primary_image:
            return self.primary_image.url
        return f"{settings.STATIC_URL}{PLACEHOLDER_PRODUCT_IMAGE}"

    def recalculate_rating(self):
        agg = self.reviews.aggregate(avg=models.Avg("rating"), count=models.Count("id"))
        self.average_rating = round(agg["avg"] or 0, 2)
        self.review_count = agg["count"] or 0
        self.save(update_fields=["average_rating", "review_count"])


class ProductImage(TimeStampedModel):
    """Additional gallery photos of the product itself (bottle, packaging, texture)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="gallery_images")
    image = models.ImageField(upload_to="products/gallery/", blank=True, null=True)
    alt_text = models.CharField(max_length=200, blank=True)
    display_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["display_order", "created_at"]

    def __str__(self):
        return f"Image for {self.product.name}"

    @property
    def image_url(self):
        if self.image:
            return self.image.url
        return f"{settings.STATIC_URL}{PLACEHOLDER_PRODUCT_IMAGE}"


class PlantGalleryImage(TimeStampedModel):
    """The small 'from the garden' photo album — the source plant growing in situ."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="plant_gallery_images")
    image = models.ImageField(upload_to="products/garden/", blank=True, null=True)
    caption = models.CharField(max_length=200, blank=True)
    display_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["display_order", "created_at"]

    def __str__(self):
        return f"Garden photo for {self.product.name}"

    @property
    def image_url(self):
        if self.image:
            return self.image.url
        return f"{settings.STATIC_URL}{PLACEHOLDER_GARDEN_IMAGE}"


class Review(TimeStampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="reviews")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="reviews")
    rating = models.PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)])
    title = models.CharField(max_length=150, blank=True)
    comment = models.TextField(blank=True)
    is_verified_purchase = models.BooleanField(default=False)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["product", "user"], name="one_review_per_user_per_product")
        ]

    def __str__(self):
        return f"{self.rating}★ {self.product.name} by {self.user.email}"


class WishlistItem(TimeStampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="wishlist_items")
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="wishlisted_by")

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["user", "product"], name="one_wishlist_entry_per_user_per_product")
        ]

    def __str__(self):
        return f"{self.user.email} ♥ {self.product.name}"
