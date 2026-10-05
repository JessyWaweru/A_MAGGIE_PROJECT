from django.test import TestCase
from rest_framework.test import APIClient

from .models import Category, Ingredient, Product, Symptom
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
