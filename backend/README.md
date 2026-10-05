# GO herbal — Backend

Django + Django REST Framework API for the herbal remedies e-commerce site.

## Stack

- Django 6, Django REST Framework
- JWT auth (`djangorestframework-simplejwt`), email verification, password reset
- `django-filter` for product search/filtering, `drf-spectacular` for API docs
- SQLite by default in dev, swap in `DATABASE_URL` for Postgres in prod
- Paystack for payments (works with M-Pesa and cards in Kenya)

## Setup

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in SECRET_KEY etc.
python manage.py migrate
python manage.py seed_products      # placeholder catalog
python manage.py createsuperuser
python manage.py runserver
```

API root: `http://127.0.0.1:8000/api/`
Interactive docs: `http://127.0.0.1:8000/api/docs/`
Admin: `http://127.0.0.1:8000/admin/`

## App layout

- `apps/accounts` — custom email-based User, JWT auth, email verification, password reset, saved addresses
- `apps/products` — Category, Symptom, Ingredient, PlantOrigin, Product, image galleries, reviews, wishlist
- `apps/orders` — Cart, CartItem, Order, OrderItem, checkout
- `apps/payments` — Paystack initialize/verify/webhook
- `apps/core` — newsletter signup, contact form, shared model mixins

## Key endpoints

| Method | Path | Notes |
|---|---|---|
| POST | `/api/auth/register/` | Returns JWT pair + sends verification email |
| POST | `/api/auth/login/` | Email + password → JWT pair |
| POST | `/api/auth/login/refresh/` | Refresh access token |
| POST | `/api/auth/verify-email/` | `{uid, token}` from the emailed link |
| POST | `/api/auth/password-reset/` / `/confirm/` | Password reset flow |
| GET | `/api/auth/me/` | Current user profile |
| GET | `/api/products/?search=headache` | Free-text search across name/description/**symptoms**/ingredients |
| GET | `/api/products/?symptom=insomnia&category=teas-infusions` | Facet filtering |
| GET | `/api/products/<slug>/` | Full detail: ingredients, plant gallery, reviews, related products |
| GET/POST | `/api/products/<slug>/reviews/` | Product reviews |
| GET/POST/DELETE | `/api/orders/cart/`, `/api/orders/cart/items/` | Cart management |
| POST | `/api/orders/checkout/` | Cart → Order |
| POST | `/api/payments/initialize/` | Order → Paystack checkout link |
| GET | `/api/payments/verify/<reference>/` | Confirms payment, marks order paid |
| POST | `/api/payments/webhook/paystack/` | Paystack server-to-server event |

## Placeholder → real content

Every product/category/plant-gallery image field falls back to a static
placeholder SVG (`static/placeholders/`) via an `*_url` property when no
image has been uploaded. Populating real data through the admin or a future
import script is a drop-in replacement — no frontend or serializer changes
needed.

## Email

`EMAIL_BACKEND` defaults to the console backend, so verification/reset/order
emails print to the terminal in dev. Switch to SMTP in `.env` for production.

## Payments

Set `PAYSTACK_SECRET_KEY` / `PAYSTACK_PUBLIC_KEY` in `.env` (test keys from
the Paystack dashboard work immediately). Without keys, `/payments/initialize/`
fails gracefully with a clear error instead of crashing.
