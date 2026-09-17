# Cafe Pont

Cafe Pont is a full-stack rewards counter for independent cafes. Staff can register, log in, search members by name or phone, record purchases, redeem rewards, and see the authoritative live points balance. Silver and Gold members earn faster without making the counter staff calculate tiers manually.

## Product

- **Target audience:** cafe counter staff and small multi-shift cafe teams.
- **Landing page:** the first screen explains the product, target audience, value, key features, and three next features.
- **Current earning rules:** Regular earns 1 point per whole dollar, Silver starts at 500 points and earns 1.5x, Gold starts at 2,000 points and earns 2x. Points are floored to whole points.
- **Redemption:** staff can redeem any positive whole-point amount up to the member's current balance. The API rejects insufficient balances atomically.
- **Next features:** member insights, a configurable rewards catalog, and multi-location support.

## Stack and schema

- React 19 + Vite frontend
- FastAPI REST API
- SQLite via `better-sqlite3`
- JWT authentication and bcrypt password hashing

SQLite creates `server/cafe-pont.db` on first API start with:

- `users`: staff login credentials and creation date
- `members`: member identity, phone, points, and lifetime spend
- `transactions`: immutable purchase/redemption ledger entries with point deltas and timestamps

The member balance is read from the `members.points` authoritative state and every mutation updates both the member and transaction ledger in one SQLite transaction.

## Setup and run

Requires Node.js 20+ and Python 3.10+.

```bash
npm install
pip install -r requirements.txt
npm run dev
```

Open `http://localhost:5173`. The development script runs Vite and the API together. Create an account from the landing page. The API runs on `http://localhost:3001` and Vite proxies `/api` requests.

Production frontend build:

```bash
npm run build
npm run server
npm run preview
```

## Deploy

The repository includes `render.yaml` for a single Render web service. In Render, choose **New + > Blueprint**, connect `b230865-rgb/Cafe-reward`, and apply the blueprint. It installs FastAPI, builds the Vite UI, serves it from Python, runs the API health check, generates `JWT_SECRET`, and mounts a 1 GB persistent disk at `server/` for SQLite. A Render Starter plan or higher is required for the persistent disk.

Useful checks:

```bash
npm run lint
curl http://localhost:3001/api/health
```

To reset local demo data, stop the API and delete `server/cafe-pont.db`; the next start seeds six members.

## REST API

Authenticated endpoints use `Authorization: Bearer <token>`.

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `POST` | `/api/auth/register` | Create a staff account; body `{ email, password }` |
| `POST` | `/api/auth/login` | Log in; body `{ email, password }` |
| `GET` | `/api/health` | API health check |
| `GET` | `/api/members?search=&sort=points&page=1&limit=5` | Search, sort, and paginate members |
| `GET` | `/api/members/:id` | Get member profile and recent ledger entries |
| `POST` | `/api/members/:id/purchase` | Record purchase; body `{ amount }` |
| `POST` | `/api/members/:id/redeem` | Redeem points; body `{ points, rewardName }` |

Supported member sorts are `points`, `name`, and `lifetime_spend_cents`. Search matches member name or phone number.

## Debugging

1. Run `npm run server` in one terminal and `npm run dev` in another if you want separate logs.
2. Check `http://localhost:3001/api/health` first.
3. Inspect the SQLite file with any SQLite browser, or query it with `sqlite3` if installed.
4. Confirm every purchase or redemption has a matching row in `transactions` and that `members.points` matches the sum of its ledger deltas from the starting balance.
