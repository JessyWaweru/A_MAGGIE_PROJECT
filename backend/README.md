# GOherbal — Backend

Django + Django REST Framework API for the herbal remedies e-commerce site.

## Stack

- Django 6, Django REST Framework
- JWT auth (`djangorestframework-simplejwt`), email verification, password reset
- `django-filter` for product search/filtering, `drf-spectacular` for API docs
- SQLite by default in dev; production runs on Render Postgres via `DATABASE_URL`
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
emails print to the terminal in dev. Production settings send through Resend's
HTTPS API instead (`apps.core.email_backend.ResendEmailBackend`): set
`RESEND_API_KEY` and leave `EMAIL_BACKEND` unset. The sending domain in
`DEFAULT_FROM_EMAIL` must be verified in Resend. SMTP won't work on Render's
free tier, which blocks outbound SMTP ports.

## Payments

Set `PAYSTACK_SECRET_KEY` / `PAYSTACK_PUBLIC_KEY` in `.env` (test keys from
the Paystack dashboard work immediately). Without keys, `/payments/initialize/`
fails gracefully with a clear error instead of crashing.

## Deployment (Render)

- **Backend**: a Render web service running this app, with a custom domain
  (`api.goherbal.health`) and the release command in `Procfile` (`migrate` +
  `seed_products`) running on every deploy.
- **Database**: a separate Render Postgres instance. Set the backend's
  `DATABASE_URL` to its *Internal* Database URL (same region = free, faster).
  Render's free Postgres tier expires after 90 days — use a paid plan for
  anything meant to persist.
- **Frontend**: the `herb-root-frontend` repo, deployed as a Render static
  site with its own custom domain (`goherbal.health` / `www`).
- Cookie-based auth requires the backend and frontend to share a registrable
  domain, hence the `api.` subdomain split above rather than two unrelated
  `*.onrender.com` hosts. `ALLOWED_HOSTS`, `CORS_ALLOWED_ORIGINS`,
  `CSRF_TRUSTED_ORIGINS` and `FRONTEND_URL` must match the real domains in
  the backend service's environment variables.
