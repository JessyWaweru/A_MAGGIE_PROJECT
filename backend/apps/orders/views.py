from decimal import Decimal

from django.db import transaction
from django.http import Http404
from django.shortcuts import get_object_or_404
from rest_framework import generics, permissions, status, viewsets
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from .models import Cart, CartItem, DeliveryOption, Order, OrderItem, rider_zone_for
from .serializers import (
    AddCartItemSerializer,
    CartSerializer,
    CheckoutSerializer,
    DeliveryOptionSerializer,
    DeliveryQuoteSerializer,
    OrderSerializer,
    RiderDeliverySerializer,
    UpdateCartItemSerializer,
)


def get_or_create_cart(user):
    cart, _ = Cart.objects.get_or_create(user=user)
    return cart


class CartView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        cart = get_or_create_cart(request.user)
        return Response(CartSerializer(cart).data)

    def delete(self, request):
        cart = get_or_create_cart(request.user)
        cart.items.all().delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class CartItemListView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = AddCartItemSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        product = serializer.validated_data["product_id"]
        quantity = serializer.validated_data["quantity"]

        cart = get_or_create_cart(request.user)
        item, created = CartItem.objects.get_or_create(cart=cart, product=product, defaults={"quantity": quantity})
        if not created:
            item.quantity += quantity
            item.save(update_fields=["quantity"])

        return Response(CartSerializer(cart).data, status=status.HTTP_201_CREATED)


class CartItemDetailView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get_item(self, request, item_id):
        return get_object_or_404(CartItem, id=item_id, cart__user=request.user)

    def patch(self, request, item_id):
        item = self.get_item(request, item_id)
        serializer = UpdateCartItemSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        item.quantity = serializer.validated_data["quantity"]
        item.save(update_fields=["quantity"])
        return Response(CartSerializer(item.cart).data)

    def delete(self, request, item_id):
        item = self.get_item(request, item_id)
        cart = item.cart
        item.delete()
        return Response(CartSerializer(cart).data)


class CheckoutView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @transaction.atomic
    def post(self, request):
        cart = get_or_create_cart(request.user)
        items = list(cart.items.select_related("product").select_for_update())
        if not items:
            return Response({"detail": "Your cart is empty."}, status=status.HTTP_400_BAD_REQUEST)

        for item in items:
            if item.quantity > item.product.stock_quantity:
                return Response(
                    {"detail": f"Only {item.product.stock_quantity} of '{item.product.name}' left in stock."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        serializer = CheckoutSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        option = data["delivery_option"]

        subtotal = sum((item.line_total for item in items), Decimal("0.00"))
        order = Order.objects.create(
            user=request.user,
            subtotal=subtotal,
            shipping_fee=option.fee,
            total_amount=subtotal + option.fee,
            currency=items[0].product.currency,
            customer_notes=data.get("customer_notes", ""),
            delivery_option=option,
            delivery_method=option.method,
            delivery_option_name=option.name,
            pickup_agent=data.get("pickup_agent", "").strip() if option.method == DeliveryOption.Method.AGENT else "",
            **data["address_fields"],
        )
        OrderItem.objects.bulk_create(
            [
                OrderItem(
                    order=order,
                    product=item.product,
                    product_name=item.product.name,
                    unit_price=item.product.price,
                    quantity=item.quantity,
                )
                for item in items
            ]
        )
        cart.items.all().delete()

        return Response(OrderSerializer(order).data, status=status.HTTP_201_CREATED)


class DeliveryOptionListView(generics.ListAPIView):
    queryset = DeliveryOption.objects.filter(is_active=True)
    serializer_class = DeliveryOptionSerializer
    permission_classes = [permissions.AllowAny]
    pagination_class = None


class DeliveryQuoteView(APIView):
    """Prices rider delivery to a map pin, so the checkout can show the fee before ordering."""

    permission_classes = [permissions.AllowAny]

    def get(self, request):
        serializer = DeliveryQuoteSerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        zone, km = rider_zone_for(serializer.validated_data["latitude"], serializer.validated_data["longitude"])
        return Response(
            {
                "available": zone is not None,
                "distance_km": round(km, 1),
                "option": DeliveryOptionSerializer(zone).data if zone else None,
            }
        )


class RiderDeliveryView(APIView):
    """The rider's private link. The token in the URL is the only credential, and it dies when
    the order is reassigned or finished. Riders can only move an order forward."""

    permission_classes = [permissions.AllowAny]
    authentication_classes = []
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "rider_link"

    # action → (statuses it's allowed from, status it moves to)
    ACTIONS = {
        "picked-up": ({Order.Status.PAID, Order.Status.PROCESSING}, Order.Status.OUT_FOR_DELIVERY),
        "delivered": (
            {Order.Status.PAID, Order.Status.PROCESSING, Order.Status.OUT_FOR_DELIVERY},
            Order.Status.DELIVERED,
        ),
    }

    @staticmethod
    def get_order(token, lock=False):
        if len(token) < 20:
            raise Http404
        queryset = Order.objects.select_related("rider").prefetch_related("items")
        if lock:
            queryset = queryset.select_for_update()
        order = queryset.filter(rider_token=token, rider__isnull=False).first()
        if order is None:
            raise Http404
        return order

    def get(self, request, token):
        return Response(RiderDeliverySerializer(self.get_order(token)).data)

    @transaction.atomic
    def post(self, request, token, action):
        if action not in self.ACTIONS:
            raise Http404
        order = self.get_order(token, lock=True)
        allowed_from, new_status = self.ACTIONS[action]
        if order.status not in allowed_from:
            return Response(
                {"detail": f"This order is already {order.get_status_display().lower()}."},
                status=status.HTTP_409_CONFLICT,
            )
        data = RiderDeliverySerializer(order).data
        order.status = new_status
        order.save()  # records the timeline step and emails the customer
        data["status"] = new_status
        return Response(data)


class OrderViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = OrderSerializer
    permission_classes = [permissions.IsAuthenticated]
    lookup_field = "order_number"

    def get_queryset(self):
        return Order.objects.filter(user=self.request.user).prefetch_related("items__product", "status_events")
