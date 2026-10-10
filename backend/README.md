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
- `apps/orders` — Cart, CartItem, Order, OrderItem, checkout, delivery options/fees, order status timeline
- `apps/payments` — Paystack initialize/verify/webhook (for orders and consultations)
- `apps/consultations` — herbal coaches and medical specialists, paid consultation bookings
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
| GET | `/api/orders/delivery-options/` | Active delivery options and fees |
| GET | `/api/orders/delivery-quote/?latitude=&longitude=` | Rider zone and fee for a map pin |
| POST | `/api/orders/checkout/` | `delivery_method` (`pickup` / `rider` / `agent`) plus contact, address and pin |
| GET | `/api/consultations/experts/?kind=herbal_coach` | Public expert profiles |
| POST | `/api/consultations/bookings/` | Book a session (unpaid); pay with `/api/payments/initialize/` + `consultation_reference` |
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

## Receiving email

Mail to any `@goherbal.health` address reaches `/api/webhooks/inbound-email/` through Resend
inbound. It's saved in the admin (**Core → Inbound emails**) and forwarded to
`INBOUND_FORWARD_TO`, with Reply going to the original sender. The forwarding address must be on
another domain, because forwarding to `@goherbal.health` would loop back through the webhook.

## Delivery

Delivery options and fees are edited in the admin (**Orders → Delivery options**); a
migration seeds placeholder ones. There are three methods:

- **Store pickup**: a CBD shop (placeholder address and fee).
- **Rider**: Nairobi zones priced by straight-line distance from the dispatch point
  (`DISPATCH_LATITUDE` / `DISPATCH_LONGITUDE`, default Nairobi CBD) to the customer's map pin.
  The fee is always worked out on the server from the pin.
- **Agent**: Pickup Mtaani-style collection points across the country, at a flat fee.

When staff change an order's status in the admin, the change is added to the order's
timeline, and the customer is emailed for ready-for-pickup, out-for-delivery,
sent-to-agent and delivered. Order pages in the admin link riders to the customer's pin
in Google Maps.

### Riders

Riders are added in the admin (**Orders → Riders**) and don't need an account. Choosing a rider
on a paid rider-delivery order texts them a private link through Africa's Talking
(`AFRICASTALKING_*` settings). The link opens a phone page with the customer, address, directions,
a Navigate button and **Picked up** / **Delivered** buttons. The buttons move the order along, so
the timeline updates and the customer is emailed, including the rider's name and number. A link
stops working when the order is given to another rider or is delivered. If the SMS fails, the
admin says so, and **Resend delivery link** retries.

## Consultations

Experts are added in the admin (**Consultations → Experts**). Medical specialists need a
licence number. Sessions are by email, phone or video; all arranging happens by email.
Customers book with a preferred time and their concern, and the booking is
confirmed once Paystack payment succeeds. The customer, the expert's private email and
`CONSULTATIONS_TEAM_EMAIL` (optional) are then emailed. Staff set the confirmed time and any
video link on the booking. A booking's concern is health information, so only the customer,
the assigned expert and admins see it.

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
