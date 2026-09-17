# Cafe Pont

Cafe Pont is a full-stack rewards counter for independent cafes and small café chains. Staff can register, log in, find members by name or phone, record purchases, redeem rewards, and see the authoritative live points balance. Tier-aware earning, expiring point lots, and an integration outbox keep the rewards ledger predictable as the programme grows.

## What is included

- A React/Vite counter UI with a one-page product landing screen.
- A Python FastAPI REST backend with JWT authentication and bcrypt password hashing.
- A SQLite database with transactional balance updates and an auditable points ledger.
- Member search, pagination, and sorting for a long member list.
- Regular, Silver, Gold, and Platinum earning rules.
- 90-day unused-points expiration through a deterministic clock endpoint.
- Tier-change notifications written to an outbox for a future notification worker.

## Product

- **Target audience:** cafe counter staff and small multi-shift cafe teams.
- **Landing page:** the first screen explains the product, target audience, value, key features, and three next features.
- **Current earning rules:** Regular earns 1 point per whole dollar, Silver starts at 500 points and earns 1.5x, Gold starts at 2,000 points and earns 2x. Points are floored to whole points.
- **Platinum:** lifetime spend of at least 5,000 currency units qualifies the member; Platinum earns 0.3 points per currency unit. Lifetime spend is stored in cents, so the threshold is 500,000 cents.
- **Redemption:** staff can redeem any positive whole-point amount up to the member's current balance. The API rejects insufficient balances atomically.
- **Expiration:** unused points expire after 90 days. Point grants are tracked as lots, and `POST /clock` runs the deterministic expiration job.
- **Notifications:** entering a new tier writes a `tier.changed` event to the notification outbox exposed at `/outbox`.
- **Next features:** member insights, a configurable rewards catalog, and multi-location support.

## Stack and data model

- React 19 + Vite frontend
- FastAPI REST API
- SQLite via Python's standard `sqlite3` module
- JWT authentication and bcrypt password hashing

SQLite creates `server/cafe-pont.db` on first local API start with:

- `users`: staff login credentials and creation date
- `members`: member identity, phone, points, and lifetime spend
- `transactions`: immutable purchase/redemption ledger entries with point deltas and timestamps
- `point_lots`: each points grant and its remaining unexpired amount
- `notifications_outbox`: tier-change events waiting for a notification service

The authoritative live balance is `members.points`. Purchase, redemption, and expiration operations update the balance and ledger in one SQLite transaction. Point lots make expiration and oldest-first redemption auditable instead of guessing from an aggregate balance.

## Setup and run

Requires Node.js 20+ and Python 3.10+.

```bash
npm install
python -m pip install -r requirements.txt
npm run dev
```

Open the Vite URL printed in the terminal, normally `http://localhost:5173`. The development script runs Vite and FastAPI together. Create an account from the landing page. FastAPI runs on `http://localhost:3001`, and Vite proxies `/api` requests to it.

Production frontend build:

```bash
npm run build
npm run server
```

The production server serves the built UI and API from `http://localhost:3001`.

## Deploy

The repository includes `render.yaml` for a single native Render Python web service. In Render, choose **New + > Blueprint**, connect `b230865-rgb/Cafe-reward`, and apply the blueprint. Render installs the Python requirements, builds the Vite UI with npm, runs FastAPI, generates `JWT_SECRET`, and mounts a 1 GB persistent disk at `/var/data` for SQLite. A Render Starter plan or higher is required for the persistent disk. After pushing changes, use **Manual Deploy > Deploy latest commit** in Render.

Useful checks:

```bash
npm run lint
curl http://localhost:3001/api/health
```

To reset local demo data, stop the API and delete `server/cafe-pont.db`; the next start seeds six members.

## REST API

Authenticated endpoints use `Authorization: Bearer <token>`. Registration and login return the JWT token.

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `POST` | `/api/auth/register` | Create a staff account; body `{ email, password }` |
| `POST` | `/api/auth/login` | Log in; body `{ email, password }` |
| `GET` | `/api/health` | API health check |
| `GET` | `/api/members?search=&sort=points&page=1&limit=5` | Search, sort, and paginate members |
| `GET` | `/api/members/:id` | Get member profile and recent ledger entries |
| `POST` | `/api/members/:id/purchase` | Record purchase; body `{ amount }` |
| `POST` | `/api/members/:id/redeem` | Redeem points; body `{ points, rewardName }` |
| `POST` | `/clock` or `/api/clock` | Expire unused point lots; body `{ "now": "2030-01-01T00:00:00Z" }`, `{ "advanceDays": 91 }`, or `{}` |
| `GET` / `POST` | `/outbox` or `/api/outbox` | Read tier-change notification events as JSON |

Supported member sorts are `points`, `name`, and `lifetime_spend_cents`. Search matches member name or phone number.

## Rewards rules

| Tier | Qualification | Purchase earning |
| --- | --- | --- |
| Regular | Below 500 points and below Platinum lifetime spend | 1 point per currency unit |
| Silver | At least 500 points | 1.5 points per currency unit |
| Gold | At least 2,000 points | 2 points per currency unit |
| Platinum | Lifetime spend of at least 5,000 currency units | 0.3 points per currency unit |

Points are stored as whole integers. Currency is stored as cents. Platinum is checked before the existing point tiers, so members who do not meet its lifetime-spend threshold keep their previous tier and balance behavior.

## Debugging and validation

1. Run `npm run server` in one terminal and `npm run dev` in another if you want separate logs.
2. Check `http://localhost:3001/api/health` first.
3. Inspect the SQLite file with any SQLite browser, or query it with `sqlite3` if installed.
4. Confirm every purchase, redemption, or expiration has a matching row in `transactions`.
5. Check `point_lots` when debugging expiration or redemption allocation.

The implemented validation includes Python compilation, the React production build, API smoke tests for registration/login/search/purchase/redemption, Platinum qualification, exact Platinum earning, outbox creation, 90-day expiration, and repeated-clock idempotency.
