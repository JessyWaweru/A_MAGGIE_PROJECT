"""Natural-language product search.

Understands free text like "no sleep", "my tummy hurts" or "ginger tea for a cough":
it detects the concerns (symptoms) being described, tolerates typos, and ranks
products by how many of the query's meaningful words they match (OR, not AND),
so one unknown word never zeroes out the results.
"""

import re
from dataclasses import dataclass, field

STOPWORDS = {
    "a", "about", "after", "all", "am", "an", "and", "any", "are", "as", "at", "be", "been", "being",
    "best", "can", "cant", "could", "do", "does", "dont", "for", "from", "get", "getting", "give", "good",
    "got", "have", "having", "help", "helps", "i", "im", "in", "is", "it", "its", "ive", "just", "keep",
    "lot", "lots", "me", "much", "my", "need", "no", "not", "of", "on", "or", "please", "really", "so",
    "some", "something", "that", "the", "these", "this", "to", "too", "very", "want", "what", "when",
    "with", "without", "wont", "you", "your", "feel", "feeling", "feels", "always", "keeps", "since",
    "remedy", "remedies", "herbal", "herb", "herbs", "natural", "product", "products", "bit", "kind",
}

# Weighted vocabulary per symptom slug. Terms match whole words, word prefixes
# (so "ache" catches "aches"), or near-misses (typos).
SYMPTOM_VOCAB: dict[str, dict[str, float]] = {
    "insomnia": {
        "insomnia": 3, "sleep": 3, "sleeping": 3, "asleep": 3, "sleepless": 3, "slept": 3,
        "awake": 2, "bedtime": 2, "restless": 1.5, "night": 1, "nights": 1, "rest": 1, "wake": 1.5,
    },
    "headache": {
        "headache": 3, "migraine": 3, "head": 2, "throbbing": 1.5, "temple": 1.5, "tension": 1,
    },
    "stress-anxiety": {
        "stress": 3, "stressed": 3, "anxiety": 3, "anxious": 3, "panic": 3, "worried": 2, "worry": 2,
        "nervous": 2, "overwhelmed": 2, "calm": 2, "relax": 2, "relaxing": 2, "tense": 1.5,
        "mood": 1.5, "racing": 1, "mind": 0.5, "edge": 0.5,
    },
    "digestive-issues": {
        "digestion": 3, "digestive": 3, "stomach": 3, "tummy": 3, "belly": 3, "gut": 3, "bloating": 3,
        "bloated": 3, "nausea": 3, "nauseous": 3, "indigestion": 3, "constipation": 3, "constipated": 3,
        "diarrhea": 3, "heartburn": 3, "gas": 2, "cramps": 1,
    },
    "cold-flu": {
        "cold": 3, "flu": 3, "cough": 3, "coughing": 3, "congestion": 3, "congested": 3, "sneezing": 3,
        "throat": 2.5, "runny": 2, "stuffy": 2, "nose": 1.5, "fever": 2.5, "chills": 2, "sinus": 2.5,
        "catarrh": 3,
    },
    "joint-pain": {
        "joint": 3, "joints": 3, "arthritis": 3, "knee": 2.5, "knees": 2.5, "back": 2, "stiff": 2,
        "stiffness": 2, "inflammation": 2.5, "inflamed": 2.5, "muscle": 1.5, "sore": 1, "pain": 1,
    },
    "low-energy": {
        "energy": 3, "tired": 3, "fatigue": 3, "fatigued": 3, "exhausted": 3, "sluggish": 3,
        "drained": 2.5, "weak": 2, "lethargic": 3, "focus": 1.5, "boost": 1.5,
    },
    "skin-irritation": {
        "skin": 3, "rash": 3, "itchy": 3, "itching": 3, "acne": 3, "pimples": 3, "eczema": 3,
        "irritation": 2, "irritated": 2, "dry": 1, "redness": 2, "blemish": 2.5, "burn": 1.5, "sunburn": 3,
    },
    "menstrual-discomfort": {
        "period": 3, "periods": 3, "menstrual": 3, "menstruation": 3, "cramps": 2.5, "pms": 3, "cycle": 2,
    },
    "immune-support": {
        "immune": 3, "immunity": 3, "defence": 2, "defense": 2, "sick": 2, "resilience": 1.5,
    },
}

# How much a product earns for each match source. A detected concern is the
# strongest signal; a word in the name/ingredients beats one buried in prose.
CONCERN_WEIGHT = 4.0
FIELD_WEIGHTS = {"name": 3.0, "ingredients": 3.0, "category": 2.0, "summary": 1.0, "description": 0.5}
MIN_CONCERN_SCORE = 2.0
RELATIVE_CUTOFF = 0.25


def tokenize(text: str) -> list[str]:
    text = re.sub(r"['’]", "", text.lower())
    return [t for t in re.split(r"[^a-z0-9]+", text) if t]


def meaningful_tokens(text: str) -> list[str]:
    return [t for t in tokenize(text) if t not in STOPWORDS and len(t) > 1]


def _edit_distance(a: str, b: str, limit: int) -> int:
    """Levenshtein distance, bailing out early once it exceeds `limit`."""
    if abs(len(a) - len(b)) > limit:
        return limit + 1
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        if min(cur) > limit:
            return limit + 1
        prev = cur
    return prev[-1]


def word_matches(token: str, term: str) -> float:
    """1.0 for an exact/stem match, 0.8 for a likely typo, 0 otherwise."""
    if token == term:
        return 1.0
    shorter, longer = sorted((token, term), key=len)
    if len(shorter) >= 4 and longer.startswith(shorter):
        return 1.0
    # Short words are too easy to confuse ("ache" vs "acne"), so only fuzz longer ones.
    if len(token) < 5 or len(term) < 5:
        return 0.0
    allowed = 1 if max(len(token), len(term)) <= 6 else 2
    return 0.8 if _edit_distance(token, term, allowed) <= allowed else 0.0


def best_match(token: str, words) -> float:
    return max((word_matches(token, w) for w in words), default=0.0)


def detect_concerns(tokens: list[str], symptoms) -> dict[str, float]:
    """Map query tokens to symptom slugs with a confidence score."""
    scores: dict[str, float] = {}
    for symptom in symptoms:
        vocab = dict(SYMPTOM_VOCAB.get(symptom.slug, {}))
        # Symptoms added later through the admin are still recognised by name.
        for word in meaningful_tokens(symptom.name):
            vocab.setdefault(word, 2.0)
        score = 0.0
        for token in tokens:
            hits = [weight * word_matches(token, term) for term, weight in vocab.items()]
            score += max(hits, default=0.0)
        if score >= MIN_CONCERN_SCORE:
            scores[symptom.slug] = score
    return scores


@dataclass
class ScoredProduct:
    product: object
    score: float
    matched_concerns: list[str] = field(default_factory=list)


def _product_fields(product) -> dict[str, set[str]]:
    return {
        "name": set(tokenize(product.name)),
        "ingredients": {w for i in product.ingredients.all() for w in tokenize(i.name)},
        "category": set(tokenize(product.category.name)) if product.category else set(),
        "summary": set(tokenize(f"{product.short_description} {product.how_it_helps}")),
        "description": set(tokenize(product.description)),
    }


def rank_products(query: str, products, symptoms) -> tuple[list[ScoredProduct], dict[str, float]]:
    tokens = meaningful_tokens(query)
    if not tokens:
        return [], {}

    concerns = detect_concerns(tokens, symptoms)
    ranked: list[ScoredProduct] = []

    for product in products:
        product_concerns = [s.slug for s in product.symptoms.all() if s.slug in concerns]
        score = sum(CONCERN_WEIGHT * min(concerns[slug], 6.0) / 3.0 for slug in product_concerns)

        fields = _product_fields(product)
        for token in tokens:
            score += max(
                (FIELD_WEIGHTS[name] * best_match(token, words) for name, words in fields.items()),
                default=0.0,
            )

        if score > 0:
            ranked.append(ScoredProduct(product, score, product_concerns))

    ranked.sort(key=lambda r: (-r.score, -float(r.product.average_rating), r.product.name))
    # Drop weak incidental hits (e.g. one word in a long description) when strong matches exist.
    if ranked:
        cutoff = ranked[0].score * RELATIVE_CUTOFF
        ranked = [r for r in ranked if r.score >= cutoff]
    return ranked, concerns
