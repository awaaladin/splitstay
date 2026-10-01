# SplitStay

Group contribution and bill-payment platform for the Nigerian market (the digital *ajo/esusu*). Members pool money toward rent, electricity (NEPA/disco) bills, subscriptions, family upkeep or anything custom; once the target is met the platform pays the bill or the recipient directly. It is not a lending product: nothing is ever paid on a member's behalf in advance.

One Django project serves both the **REST API** (`/api/v1/`, JWT, for mobile/web clients) and a **server-rendered web app** (Django templates + Tailwind + Alpine.js + HTMX). Both call the same service layer, so the money rules exist in one place.

## Stack

Python 3.12 · Django 5 · DRF · SimpleJWT · drf-spectacular · PostgreSQL · Redis · Celery + Beat · Tailwind CSS 3 · Alpine.js · HTMX

## Run with Docker

```bash
docker-compose up --build            # web, db, redis, celery worker, celery beat
docker-compose exec web python manage.py seed_demo
```

Open http://localhost:8000. Migrations run automatically on `web` start. Demo login: `ada@demo.splitstay.test` / `demo12345` (also `tunde@`, `chioma@`, `ibrahim@`, `ngozi@` at the same domain).

- API docs (Swagger): http://localhost:8000/api/docs/ · schema: http://localhost:8000/api/schema/
- Defaults use the **mock** payment gateway and bill provider: checkout is a sandbox page, no real money moves. Set `PAYMENT_GATEWAY=paystack`, `PAYSTACK_SECRET_KEY`, `BILL_PROVIDER=vtpass` and the VTpass keys for real integrations (see `.env.example`).

## Run without Docker (SQLite, no Redis)

```bash
python -m venv .venv && .venv\Scripts\activate      # source .venv/bin/activate on macOS/Linux
pip install -r requirements.txt
set DATABASE_URL=sqlite:///db.sqlite3               # use `export` on macOS/Linux
set DJANGO_CACHE=locmem
set CELERY_EAGER=1                                   # run tasks inline; no worker needed
python manage.py migrate
python manage.py seed_demo                           # --reset to wipe and recreate
python manage.py runserver
```

## Tests

```bash
python manage.py test apps --settings=config.settings.test    # SQLite, no services required
```

The highest-risk areas have dedicated tests: contribution totals (`apps/contributions/tests.py`), the funded-threshold trigger and webhook idempotency (`apps/payments/tests.py`), recurring regeneration (`apps/recurrence/tests.py`), fees and bill payments (`apps/payouts/tests.py`), plus permissions, auth, encryption, reminders and the web flows.

## Frontend

> Building or changing the UI? Read [DESIGN_AND_MOTION_GUIDE.md](DESIGN_AND_MOTION_GUIDE.md) first. It documents the animations, the user flow and the traps.

Tailwind is configured in `tailwind.config.js` with an explicit palette (navy, charcoal ink, semantic tokens; no default blue/gray) and class-based dark mode. The compiled `static/css/app.css` is committed so the site runs without Node. To change styles:

```bash
npm install
npm run watch:css      # or: npm run build:css
```

Alpine.js and HTMX are vendored in `static/vendor/`. Icons are inline Lucide outlines (`apps/web/templatetags/cp.py`).

## Deploy to Vercel

The repo is Vercel-ready: `api/index.py` (WSGI entry), `vercel.json` (rewrites, 60s function limit, crons) and `config/settings/vercel.py`.

Vercel is serverless, so two things differ from the Docker setup:
- **No Celery worker/Beat.** Tasks run inline in the request, and Vercel Cron calls `/api/cron/<task>/` (protected by `CRON_SECRET`) for deadlines, recurring cycles, reminders and payout reconciliation. All four jobs are scheduled once a day so they fit Vercel's Hobby plan. On Pro you can run the payout-reconcile job more often (e.g. `*/10 * * * *`) in `vercel.json`.
- **No persistent disk.** Avatar uploads aren't kept. Static files are served by WhiteNoise from the source tree.

Steps:
1. Create a hosted Postgres (Neon, Supabase, Vercel Postgres) and, optionally, an Upstash Redis for shared rate limits.
2. Run migrations from your machine against it: `DATABASE_URL=<url> DJANGO_SETTINGS_MODULE=config.settings.dev python manage.py migrate`
3. In the Vercel project, set these environment variables:

| Variable | Notes |
|---|---|
| `DJANGO_SETTINGS_MODULE` | `config.settings.vercel` |
| `DJANGO_SECRET_KEY` | long random string |
| `FIELD_ENCRYPTION_KEY` | Fernet key (see `.env.example`); losing it makes saved bank numbers unreadable |
| `DATABASE_URL` | Postgres URL |
| `CRON_SECRET` | long random string; Vercel sends it as the cron Bearer token |
| `PAYMENT_GATEWAY` / `PAYSTACK_SECRET_KEY` | `paystack` for real money |
| `BILL_PROVIDER` / `VTPASS_*` | `vtpass` for real bills |
| `SITE_URL` | your public URL, used for gateway callbacks |
| `CORS_ALLOWED_ORIGINS` | web/mobile origins that call the API |
| `REDIS_URL` | optional (Upstash `rediss://` URL) |
| `ALLOW_DEMO_MODE` | `1` only for a demo deployment using the mock gateway |

4. `vercel --prod` (or connect the Git repo). Point Paystack's webhook at `https://<your-domain>/api/v1/payments/webhooks/paystack/`.
5. Optional demo data: `python manage.py seed_demo` with the same `DATABASE_URL`.

## Layout

| App | Responsibility |
|---|---|
| `accounts` | Custom user (email or phone login), Profile, encrypted bank account |
| `groups` | ContributionGroup, GroupMembership, share splitting, permissions, deadlines task |
| `contributions` | Contribution rows; totals are always summed from confirmed rows |
| `payments` | Gateway interface (Paystack + mock), webhook endpoint, confirmation, funding trigger |
| `billpay` | `BillProvider` interface, VTpass + mock providers, biller catalog, `BillPayment` |
| `payouts` | Bank-transfer `Payout`, explicit `Fee` records, payout orchestration and reconciliation |
| `recurrence` | Celery Beat task that opens the next cycle with the same members and split |
| `notifications` | In-app notifications; per-channel `NotificationDelivery` so push/SMS need no schema change |
| `ledger` | Per-group and per-user history, derived at read time, visible to all members |
| `web` | Server-rendered pages, HTMX partials, seed command |

## Design decisions worth knowing

- **Funded total is never stored.** `Contribution.objects.total()` sums confirmed rows.
- **Webhook idempotency has two layers.** A unique `(provider, event_id)` row skips re-deliveries; independently, confirmation locks the contribution row and moves it to `paid` once. A group flips to `funded` under a row lock, so the payout is requested exactly once (`Payout`/`BillPayment` are one-to-one with the group).
- **Money movement happens in Celery, never inside a DB transaction.** If a gateway or biller times out the outcome is *unknown*: the record stays `processing` and a Beat task reconciles it by reference. Only an explicit rejection marks it `failed`, and a retry uses a fresh reference.
- **Fees are explicit.** Configurable flat or percentage (`SERVICE_FEE_*`), deducted from the pooled amount at payout, stored as a `Fee` row, shown as its own ledger and receipt line. Set the target slightly higher if a bill must be covered in full.
- **Members and shares lock after the first payment**, and a group with money in it can't be cancelled (there is no refund flow in this version). Payments that arrive in an unusual state (group already closed, overpayment, short payment) are flagged `needs_review` instead of being lost.
- **Recurrence** offsets each cycle from the series anchor date, so a 31 Jan group lands on 28 Feb then 31 Mar.
- Bank account numbers are Fernet-encrypted at rest (`FIELD_ENCRYPTION_KEY`; required in production).

## Not included

Flutterwave gateway implementation (the `PaymentGateway` interface is ready for it), refunds, push/SMS senders (register handlers in `notifications/services.py`), and other bill categories (add rows to `billpay/catalog.py`).

Web pages use session auth (CSRF-protected); the API is fully token-based. Production settings: `DJANGO_SETTINGS_MODULE=config.settings.prod` with `python manage.py collectstatic`.
