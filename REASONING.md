# Reasoning

## Product shape

The counter's most important promise is that a member's balance is exact. I therefore treated rewards as a domain and persistence problem before a UI problem. The UI is intentionally split into a searchable member list and a detail panel so staff can repeatedly perform the same counter workflow without losing context. The landing screen explains the product before staff enter the counter.

## Accounting decisions

Members have a stored integer `points` balance. Purchases store cents and calculate whole points from an explicit tier multiplier. The rules are Regular at 1x below 500 points, Silver at 1.5x from 500 points, Gold at 2x from 2,000 points, and Platinum at 0.3x after 5,000 currency units of lifetime spend. Redemption validates a positive integer and the current balance before mutation.

The purchase and redemption updates are wrapped in SQLite transactions. Each operation also inserts an immutable transaction row, giving the UI an activity history and giving debugging a way to reconcile the balance. Rejected redemptions return before any write, so insufficient points cannot create a negative balance.

## Twist implementation

Platinum is evaluated before the existing point-based tiers using lifetime spend in cents. The original seeded members remain unchanged because none reaches 500,000 cents. The purchase multiplier is calculated with integer arithmetic, including Platinum's exact 0.3 points per currency unit rate.

Points are represented by `point_lots`, so a clock run can expire only the unused portion of grants older than 90 days. Redemptions consume lots oldest-first, while `POST /clock` writes expiration ledger entries and is idempotent when called repeatedly for the same time.

Tier transitions are emitted by a small Notification Service boundary that writes JSON events to `notifications_outbox`. Both `/outbox` and `/api/outbox` expose the pending event stream for integration tests and future delivery workers.

## Delivery sequence

1. Scaffolded a React/Vite frontend and added FastAPI, SQLite, bcrypt, JWT, and concurrent development dependencies.
2. Created the SQLite schema and seed members in `server/main.py`.
3. Added registration/login, authenticated member queries, search, sorting, pagination, purchase, redemption, and health endpoints.
4. Replaced the starter screen with the landing/auth flow and the counter workflow.
5. Added responsive visual design for desktop counter use and smaller screens.
6. Replaced the starter README with setup, debugging, schema, product, and complete endpoint documentation.

## Testing and fixes

The first production build exposed a TypeScript error caused by `verbatimModuleSyntax`; `FormEvent` was changed to a type-only import. The next build exposed accidental `+` patch markers in two responsive CSS selectors; those were removed. The final `npm run build` completed successfully and emitted the Vite production bundle.

The API smoke test verified registration, login, member lookup, purchase, and redemption. A second isolated integration test verified Gold-to-Platinum qualification, 30 points from a 100-unit Platinum purchase, one outbox event, 90-day expiration, and zero duplicate expiration on a repeated clock run. The frontend production build and Python compilation also pass. The local SQLite database and Python bytecode are ignored and should not be committed.

## Tradeoffs and risks

This submission uses a local SQLite file for simple real persistence and a clear transactional boundary. Render deployment uses a persistent disk mounted at `/var/data`. A production multi-location deployment would move this schema to PostgreSQL, add server-side rate limiting, and make earning/redemption policies configurable per cafe. Phone numbers are currently searched using their stored presentation form; a future migration should store a canonical digits-only search column and enforce country-aware uniqueness.

## Backend migration

The backend was migrated from Express to Python FastAPI without changing the frontend API contract. The FastAPI service keeps the same REST paths, SQLite tables, JWT payload, error shape, and atomic rewards operations. Python smoke testing verified health, registration, member search, purchase earning, and redemption against the existing database.
