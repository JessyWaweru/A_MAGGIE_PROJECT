from rest_framework.routers import DefaultRouter

from django.urls import include, path

from .views import (
    CartItemDetailView,
    CartItemListView,
    CartView,
    CheckoutView,
    DeliveryOptionListView,
    DeliveryQuoteView,
    OrderViewSet,
)

router = DefaultRouter()
router.register("orders", OrderViewSet, basename="order")

urlpatterns = [
    path("cart/", CartView.as_view(), name="cart-detail"),
    path("cart/items/", CartItemListView.as_view(), name="cart-item-list"),
    path("cart/items/<uuid:item_id>/", CartItemDetailView.as_view(), name="cart-item-detail"),
    path("checkout/", CheckoutView.as_view(), name="checkout"),
    path("delivery-options/", DeliveryOptionListView.as_view(), name="delivery-option-list"),
    path("delivery-quote/", DeliveryQuoteView.as_view(), name="delivery-quote"),
    path("", include(router.urls)),
]
