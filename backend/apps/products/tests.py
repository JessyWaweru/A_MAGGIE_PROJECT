import io

from django.test import TestCase
from rest_framework.test import APIClient

from .models import Category, Ingredient, Product, Review, Symptom
from .search import word_matches


class WordMatchTests(TestCase):
    def test_exact_prefix_and_typo(self):
        self.assertEqual(word_matches("sleep", "sleep"), 1.0)
        self.assertEqual(word_matches("headaches", "headache"), 1.0)
        self.assertGreater(word_matches("slepp", "sleep"), 0)
        self.assertGreater(word_matches("insomina", "insomnia"), 0)

    def test_short_words_are_not_fuzzed(self):
        self.assertEqual(word_matches("ache", "acne"), 0.0)


class SmartSearchEndpointTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        insomnia = Symptom.objects.create(name="Insomnia")
        digestion = Symptom.objects.create(name="Digestive Issues")
        teas = Category.objects.create(name="Teas & Infusions")
        ginger = Ingredient.objects.create(name="Ginger Root")

        cls.sleep_tea = Product.objects.create(name="Chamomile Dream Tea", price=450, category=teas)
        cls.sleep_tea.symptoms.add(insomnia)
        cls.ginger_tea = Product.objects.create(name="Ginger Digestive Tea", price=380, category=teas)
        cls.ginger_tea.symptoms.add(digestion)
        cls.ginger_tea.ingredients.add(ginger)
        Product.objects.create(name="Hidden Draft", price=100, status=Product.Status.DRAFT).symptoms.add(insomnia)

    def search(self, q):
        return APIClient().get("/api/products/smart-search/", {"q": q}).json()

    def names(self, data):
        return [r["name"] for r in data["results"]]

    def test_natural_phrasing_maps_to_concern(self):
        for q in ["no sleep", "I can't sleep", "slepp", "insomina"]:
            data = self.search(q)
            self.assertFalse(data["fallback"], q)
            self.assertEqual([c["slug"] for c in data["concerns"]], ["insomnia"], q)
            self.assertEqual(self.names(data), ["Chamomile Dream Tea"], q)

    def test_matches_any_word_not_all(self):
        data = self.search("ginger something unknown")
        self.assertEqual(self.names(data)[0], "Ginger Digestive Tea")

    def test_unmatched_query_falls_back_without_being_empty(self):
        data = self.search("xyzzy")
        self.assertTrue(data["fallback"])
        self.assertEqual(data["count"], 0)
        self.assertTrue(data["results"])

    def test_inactive_products_are_excluded(self):
        self.assertNotIn("Hidden Draft", self.names(self.search("sleep")))


class ReviewerNameTests(TestCase):
    def name_for(self, **user_fields):
        from apps.accounts.models import User

        from .models import Review
        from .serializers import ReviewSerializer

        user = User.objects.create_user(email="jane.doe1990@example.com", password="x", **user_fields)
        product = Product.objects.create(name=f"Tea {User.objects.count()}", price=100)
        review = Review.objects.create(product=product, user=user, rating=5, comment="Lovely")
        return ReviewSerializer(review).data["user_name"]

    def test_shows_first_name_and_initial_only(self):
        self.assertEqual(self.name_for(first_name="Jane", last_name="Doe"), "Jane D.")

    def test_never_shows_email(self):
        self.assertEqual(self.name_for(), "GOherbal customer")


class VerifiedPurchaseReviewTests(TestCase):
    def setUp(self):
        from apps.accounts.models import User

        self.user = User.objects.create_user(email="amina@example.com", password="x", first_name="Amina")
        self.product = Product.objects.create(name="Moringa Leaf Powder", price=600)
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def buy(self, status):
        from django.utils import timezone

        from apps.orders.models import Order, OrderItem

        order = Order.objects.create(user=self.user, delivery_method="pickup", status=status, paid_at=timezone.now())
        OrderItem.objects.create(order=order, product=self.product, product_name=self.product.name, unit_price=600, quantity=1)

    def review(self):
        res = self.client.post(f"/api/products/{self.product.slug}/reviews/", {"rating": 5}, format="json")
        self.assertEqual(res.status_code, 201)
        return Review.objects.get(user=self.user, product=self.product).is_verified_purchase

    def test_delivered_order_counts_as_verified(self):
        self.buy("delivered")
        self.assertTrue(self.review())

    def test_refunded_order_does_not_count(self):
        self.buy("refunded")
        self.assertFalse(self.review())

    def test_no_order_is_not_verified(self):
        self.assertFalse(self.review())

    def test_product_page_marks_only_your_own_review(self):
        from apps.accounts.models import User

        self.review()
        other = APIClient()
        other.force_authenticate(User.objects.create_user(email="baraka@example.com", password="x"))
        url = f"/api/products/{self.product.slug}/"
        self.assertTrue(self.client.get(url).json()["reviews"][0]["is_mine"])
        self.assertFalse(other.get(url).json()["reviews"][0]["is_mine"])
        self.assertFalse(APIClient().get(url).json()["reviews"][0]["is_mine"])


class ConcernEndpointTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.insomnia = Symptom.objects.create(name="Insomnia", intro="Chamomile has long been sipped before bed.")
        teas = Category.objects.create(name="Teas & Infusions")
        Product.objects.create(name="Chamomile Dream Tea", price=450, category=teas).symptoms.add(cls.insomnia)
        Product.objects.create(name="Hidden Draft", price=100, category=teas, status=Product.Status.DRAFT).symptoms.add(
            cls.insomnia
        )

    def test_counts_only_products_customers_can_see(self):
        client = APIClient()
        self.assertEqual(client.get("/api/symptoms/").json()[0]["product_count"], 1)
        self.assertEqual(client.get("/api/categories/").json()[0]["product_count"], 1)
        product = client.get("/api/products/chamomile-dream-tea/").json()
        self.assertEqual(product["symptoms"][0]["product_count"], 1)
        self.assertEqual(product["category"]["product_count"], 1)

    def test_lists_keep_their_order(self):
        Symptom.objects.create(name="Acne")
        Symptom.objects.create(name="Zinc Deficiency")
        names = [s["name"] for s in APIClient().get("/api/symptoms/").json()]
        self.assertEqual(names, sorted(names))

    def test_concern_page_data_by_slug(self):
        data = APIClient().get("/api/symptoms/insomnia/").json()
        self.assertEqual(data["name"], "Insomnia")
        self.assertEqual(data["intro"], "Chamomile has long been sipped before bed.")


class ConcernIntroTests(TestCase):
    def test_seed_fills_intros_without_overwriting_edits(self):
        from django.core.management import call_command

        from .concern_intros import CONCERN_INTROS

        Symptom.objects.create(name="Insomnia", intro="Written by our team.")
        call_command("seed_products", stdout=io.StringIO())
        self.assertEqual(Symptom.objects.get(name="Insomnia").intro, "Written by our team.")
        self.assertEqual(Symptom.objects.get(name="Headache").intro, CONCERN_INTROS["Headache"])

    def test_intros_never_claim_to_treat_or_cure(self):
        import re

        from .concern_intros import CONCERN_INTROS

        for name, text in CONCERN_INTROS.items():
            self.assertIsNone(re.search(r"\b(cures?|treats?|heals?|prevents?|boosts?)\b", text, re.I), name)
