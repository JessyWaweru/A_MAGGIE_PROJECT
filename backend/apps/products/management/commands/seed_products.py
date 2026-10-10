from django.core.management.base import BaseCommand
from django.db import transaction

from apps.products.models import Category, Ingredient, PlantOrigin, Product, Symptom

CATEGORIES = [
    {"name": "Teas & Infusions", "icon": "🍵", "description": "Loose-leaf and bagged herbal teas for daily rituals."},
    {"name": "Tinctures & Extracts", "icon": "💧", "description": "Concentrated liquid extracts for fast absorption."},
    {"name": "Capsules & Powders", "icon": "💊", "description": "Standardized doses for on-the-go wellness."},
    {"name": "Essential Oils", "icon": "🌸", "description": "Aromatic oils for topical and inhaled use."},
    {"name": "Topical Balms", "icon": "🧴", "description": "Salves and balms for skin and muscle relief."},
]

SYMPTOMS = [
    {"name": "Headache", "icon": "🤕", "description": "Tension and mild headache relief."},
    {"name": "Insomnia", "icon": "😴", "description": "Support for falling and staying asleep."},
    {"name": "Stress & Anxiety", "icon": "😰", "description": "Calming remedies for a racing mind."},
    {"name": "Digestive Issues", "icon": "🤢", "description": "Soothing the stomach and gut."},
    {"name": "Cold & Flu", "icon": "🤧", "description": "Easing seasonal colds and congestion."},
    {"name": "Joint Pain", "icon": "🦴", "description": "Relief for aching joints and inflammation."},
    {"name": "Low Energy", "icon": "😪", "description": "Natural, non-jittery energy support."},
    {"name": "Skin Irritation", "icon": "🌿", "description": "Calming redness, dryness and minor irritation."},
    {"name": "Immune Support", "icon": "🛡️", "description": "Everyday resilience against seasonal bugs."},
    {"name": "Menstrual Discomfort", "icon": "🌙", "description": "Easing cramps and cycle-related discomfort."},
]

INGREDIENTS = [
    {"name": "Chamomile", "description": "A gentle daisy-like flower long used to unwind before bed."},
    {"name": "Ginger Root", "description": "A warming root that settles the stomach."},
    {"name": "Turmeric", "description": "A golden root rich in curcumin, valued for its anti-inflammatory reputation."},
    {"name": "Ashwagandha Root", "description": "An adaptogenic root traditionally used to ease stress."},
    {"name": "Peppermint Leaf", "description": "A cooling, minty leaf that eases tension."},
    {"name": "Valerian Root", "description": "A root traditionally used as a sleep aid."},
    {"name": "Echinacea", "description": "A prairie flower associated with immune support."},
    {"name": "Lavender Flower", "description": "A fragrant purple flower prized for its calming scent."},
    {"name": "Moringa Leaf", "description": "A nutrient-dense leaf grown widely across East Africa."},
    {"name": "Hibiscus Flower", "description": "A tart, ruby-red flower rich in antioxidants."},
    {"name": "Lemon Balm", "description": "A citrus-scented mint-family herb known for its calming effect."},
    {"name": "Licorice Root", "description": "A sweet root traditionally used to soothe the digestive tract."},
    {"name": "Aloe Vera", "description": "A succulent whose gel is prized for soothing skin."},
    {"name": "Neem Leaf", "description": "A bitter leaf traditionally used for skin purification."},
    {"name": "Holy Basil (Tulsi)", "description": "A sacred herb in Ayurveda, used to ease everyday stress."},
]

# Every herb comes from one garden, so there is a single origin.
SENSES_GARDEN = "Senses Garden"

PLANT_ORIGINS = [
    {
        "name": SENSES_GARDEN,
        "region": "",
        "country": "Kenya",
        "description": "Our own home garden, where every herb is grown and tended.",
    },
]

PRODUCTS = [
    {
        "name": "Chamomile Dream Tea",
        "category": "Teas & Infusions",
        "symptoms": ["Insomnia", "Stress & Anxiety"],
        "ingredients": ["Chamomile", "Lemon Balm"],
        "origin": SENSES_GARDEN,
        "price": "450.00",
        "short_description": "A gentle bedtime infusion to quiet a busy mind.",
        "description": "Whole dried chamomile flowers blended with lemon balm for a soft, honeyed cup best sipped an hour before bed.",
        "how_it_helps": "Traditionally used to ease restlessness and support a smoother wind-down to sleep.",
        "usage_instructions": "Steep 1 tsp in hot water for 5-7 minutes. Drink 30-60 minutes before bed.",
        "is_featured": True,
    },
    {
        "name": "Ginger Root Digestive Tea",
        "category": "Teas & Infusions",
        "symptoms": ["Digestive Issues"],
        "ingredients": ["Ginger Root"],
        "origin": SENSES_GARDEN,
        "price": "380.00",
        "short_description": "A warming cup to settle an uneasy stomach.",
        "description": "Sun-dried ginger root, sliced thin and packed for a sharp, warming brew.",
        "how_it_helps": "Used traditionally to ease bloating, nausea and general stomach discomfort after meals.",
        "usage_instructions": "Steep 1 tbsp in boiling water for 8-10 minutes.",
        "is_bestseller": True,
    },
    {
        "name": "Turmeric Gold Capsules",
        "category": "Capsules & Powders",
        "symptoms": ["Joint Pain", "Immune Support"],
        "ingredients": ["Turmeric"],
        "origin": SENSES_GARDEN,
        "price": "1200.00",
        "short_description": "Standardized turmeric for daily joint comfort.",
        "description": "Cold-milled turmeric root capsules, black-pepper enhanced for absorption.",
        "how_it_helps": "Supports the body's natural response to everyday joint stiffness and inflammation.",
        "usage_instructions": "Take 1 capsule twice daily with food.",
        "is_featured": True,
        "is_bestseller": True,
    },
    {
        "name": "Ashwagandha Calm Capsules",
        "category": "Capsules & Powders",
        "symptoms": ["Stress & Anxiety", "Low Energy"],
        "ingredients": ["Ashwagandha Root"],
        "origin": SENSES_GARDEN,
        "price": "1450.00",
        "short_description": "An adaptogen to help you meet stress on steadier footing.",
        "description": "Full-spectrum ashwagandha root, dried and encapsulated at source.",
        "how_it_helps": "Traditionally used to build resilience to daily stress without the jitters of caffeine.",
        "usage_instructions": "Take 1 capsule daily, morning or evening.",
        "is_featured": True,
    },
    {
        "name": "Peppermint Headache Roll-On",
        "category": "Essential Oils",
        "symptoms": ["Headache"],
        "ingredients": ["Peppermint Leaf"],
        "origin": SENSES_GARDEN,
        "price": "650.00",
        "short_description": "A cooling roll-on for tension headaches.",
        "description": "Steam-distilled peppermint oil in a jojoba base, in a convenient rollerball.",
        "how_it_helps": "The cooling sensation is traditionally used to ease tension around the temples and neck.",
        "usage_instructions": "Roll onto temples and the back of the neck as needed.",
    },
    {
        "name": "Valerian Night Tincture",
        "category": "Tinctures & Extracts",
        "symptoms": ["Insomnia"],
        "ingredients": ["Valerian Root"],
        "origin": SENSES_GARDEN,
        "price": "980.00",
        "short_description": "A fast-acting drop tincture for restless nights.",
        "description": "Valerian root slow-extracted in a small batch alcohol base.",
        "how_it_helps": "Used traditionally to help the body relax into sleep.",
        "usage_instructions": "Take 30 drops in water, 30 minutes before bed.",
    },
    {
        "name": "Echinacea Immune Tincture",
        "category": "Tinctures & Extracts",
        "symptoms": ["Cold & Flu", "Immune Support"],
        "ingredients": ["Echinacea"],
        "origin": SENSES_GARDEN,
        "price": "900.00",
        "short_description": "A daily drop to support seasonal resilience.",
        "description": "Echinacea root and flower, extracted together for a full-spectrum tincture.",
        "how_it_helps": "Traditionally taken at the first sign of a cold to support the immune response.",
        "usage_instructions": "Take 20-30 drops in water, up to 3 times daily.",
    },
    {
        "name": "Lavender Sleep Sachet",
        "category": "Essential Oils",
        "symptoms": ["Insomnia", "Stress & Anxiety"],
        "ingredients": ["Lavender Flower"],
        "origin": SENSES_GARDEN,
        "price": "300.00",
        "short_description": "A pillow sachet of whole dried lavender buds.",
        "description": "Hand-tied muslin sachets filled with whole lavender buds - tuck under your pillow.",
        "how_it_helps": "The scent is traditionally associated with easing anxiety and encouraging restful sleep.",
        "usage_instructions": "Place near your pillow at night. Refresh scent by gently crushing buds.",
    },
    {
        "name": "Moringa Vitality Powder",
        "category": "Capsules & Powders",
        "symptoms": ["Low Energy", "Immune Support"],
        "ingredients": ["Moringa Leaf"],
        "origin": SENSES_GARDEN,
        "price": "700.00",
        "short_description": "A nutrient-dense green powder for daily vitality.",
        "description": "Shade-dried moringa leaves, stone-milled into a fine green powder.",
        "how_it_helps": "A traditional East African staple valued for its dense nutrient profile and gentle energy support.",
        "usage_instructions": "Stir 1 tsp into water, juice or a smoothie daily.",
        "is_bestseller": True,
    },
    {
        "name": "Hibiscus Cooling Tea",
        "category": "Teas & Infusions",
        "symptoms": ["Menstrual Discomfort"],
        "ingredients": ["Hibiscus Flower"],
        "origin": SENSES_GARDEN,
        "price": "400.00",
        "short_description": "A tart, ruby-red tea traditionally sipped through the cycle.",
        "description": "Whole dried hibiscus calyces for a tart, antioxidant-rich infusion, hot or iced.",
        "how_it_helps": "Traditionally used to ease cramping and support comfort during menstruation.",
        "usage_instructions": "Steep 1 tbsp in hot water for 5 minutes, or cold-brew overnight.",
    },
    {
        "name": "Licorice Soothe Tea",
        "category": "Teas & Infusions",
        "symptoms": ["Digestive Issues"],
        "ingredients": ["Licorice Root"],
        "origin": SENSES_GARDEN,
        "price": "420.00",
        "short_description": "A naturally sweet tea to calm an unsettled gut.",
        "description": "Shredded licorice root, naturally sweet with no added sugar.",
        "how_it_helps": "Traditionally used to soothe the digestive lining after a heavy meal.",
        "usage_instructions": "Steep 1 tbsp in hot water for 5-8 minutes. Limit to one cup daily.",
    },
    {
        "name": "Aloe Vera Skin Balm",
        "category": "Topical Balms",
        "symptoms": ["Skin Irritation"],
        "ingredients": ["Aloe Vera"],
        "origin": SENSES_GARDEN,
        "price": "550.00",
        "short_description": "A cooling balm for irritated or sun-touched skin.",
        "description": "Cold-pressed aloe gel blended into a lightweight, fast-absorbing balm.",
        "how_it_helps": "Traditionally used to soothe redness, dryness and minor skin irritation.",
        "usage_instructions": "Apply a thin layer to the affected area up to twice daily.",
    },
    {
        "name": "Neem Purifying Balm",
        "category": "Topical Balms",
        "symptoms": ["Skin Irritation"],
        "ingredients": ["Neem Leaf"],
        "origin": SENSES_GARDEN,
        "price": "500.00",
        "short_description": "A purifying balm for blemish-prone skin.",
        "description": "Neem leaf extract in a shea butter base, for daily spot care.",
        "how_it_helps": "Traditionally used to help calm and purify troubled skin.",
        "usage_instructions": "Dab onto clean, dry skin once or twice daily.",
    },
    {
        "name": "Holy Basil Stress-Relief Tea",
        "category": "Teas & Infusions",
        "symptoms": ["Stress & Anxiety"],
        "ingredients": ["Holy Basil (Tulsi)"],
        "origin": SENSES_GARDEN,
        "price": "400.00",
        "short_description": "An everyday tulsi tea to steady a stressful day.",
        "description": "Whole-leaf holy basil (tulsi), a sacred Ayurvedic herb known for its calming, peppery aroma.",
        "how_it_helps": "Traditionally sipped through the day to build resilience to everyday stress.",
        "usage_instructions": "Steep 1 tsp in hot water for 5 minutes. Enjoy up to 3 cups a day.",
        "is_featured": True,
    },
]


class Command(BaseCommand):
    help = "Seed the database with placeholder categories, symptoms, ingredients and products."

    def add_arguments(self, parser):
        parser.add_argument(
            "--flush",
            action="store_true",
            help="Delete existing catalog data before seeding.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        if options["flush"]:
            self.stdout.write("Flushing existing catalog data...")
            Product.objects.all().delete()
            Category.objects.all().delete()
            Symptom.objects.all().delete()
            Ingredient.objects.all().delete()
            PlantOrigin.objects.all().delete()

        categories = {c["name"]: self._get_or_create_category(c) for c in CATEGORIES}
        symptoms = {s["name"]: self._get_or_create_symptom(s) for s in SYMPTOMS}
        ingredients = {i["name"]: self._get_or_create_ingredient(i) for i in INGREDIENTS}
        origins = {o["name"]: self._get_or_create_origin(o) for o in PLANT_ORIGINS}

        created_count = 0
        for p in PRODUCTS:
            product, created = Product.objects.get_or_create(
                name=p["name"],
                defaults={
                    "category": categories[p["category"]],
                    "plant_origin": origins[p["origin"]],
                    "price": p["price"],
                    "stock_quantity": 50,
                    "short_description": p["short_description"],
                    "description": p["description"],
                    "how_it_helps": p["how_it_helps"],
                    "usage_instructions": p["usage_instructions"],
                    "is_featured": p.get("is_featured", False),
                    "is_bestseller": p.get("is_bestseller", False),
                },
            )
            if created:
                created_count += 1
                product.symptoms.set([symptoms[name] for name in p["symptoms"]])
                product.ingredients.set([ingredients[name] for name in p["ingredients"]])

        self.stdout.write(
            self.style.SUCCESS(
                f"Seed complete: {len(categories)} categories, {len(symptoms)} symptoms, "
                f"{len(ingredients)} ingredients, {len(origins)} plant origins, "
                f"{created_count} new products (of {len(PRODUCTS)} total)."
            )
        )

    @staticmethod
    def _get_or_create_category(data):
        obj, _ = Category.objects.get_or_create(
            name=data["name"], defaults={"icon": data["icon"], "description": data["description"]}
        )
        return obj

    @staticmethod
    def _get_or_create_symptom(data):
        obj, _ = Symptom.objects.get_or_create(
            name=data["name"], defaults={"icon": data["icon"], "description": data["description"]}
        )
        return obj

    @staticmethod
    def _get_or_create_ingredient(data):
        obj, _ = Ingredient.objects.get_or_create(name=data["name"], defaults={"description": data["description"]})
        return obj

    @staticmethod
    def _get_or_create_origin(data):
        obj, _ = PlantOrigin.objects.get_or_create(
            name=data["name"],
            defaults={"region": data["region"], "country": data["country"], "description": data["description"]},
        )
        return obj
