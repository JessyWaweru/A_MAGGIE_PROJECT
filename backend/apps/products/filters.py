import django_filters as filters

from .models import Product


class ProductFilter(filters.FilterSet):
    category = filters.CharFilter(field_name="category__slug", lookup_expr="iexact")
    symptom = filters.CharFilter(field_name="symptoms__slug", lookup_expr="iexact")
    ingredient = filters.CharFilter(field_name="ingredients__slug", lookup_expr="iexact")
    min_price = filters.NumberFilter(field_name="price", lookup_expr="gte")
    max_price = filters.NumberFilter(field_name="price", lookup_expr="lte")
    in_stock = filters.BooleanFilter(method="filter_in_stock")
    is_featured = filters.BooleanFilter(field_name="is_featured")
    is_bestseller = filters.BooleanFilter(field_name="is_bestseller")

    class Meta:
        model = Product
        fields = [
            "category",
            "symptom",
            "ingredient",
            "min_price",
            "max_price",
            "in_stock",
            "is_featured",
            "is_bestseller",
        ]

    def filter_in_stock(self, queryset, name, value):
        return queryset.filter(stock_quantity__gt=0) if value else queryset.filter(stock_quantity=0)
