# AI conversation log

User: The storyline

A café chain’s rewards programme. Members earn points on every purchase and redeem them for free items. Regulars reach higher tiers — Silver, then Gold — that earn faster. The counter needs to record a purchase, add the right points, let a member redeem, and always show the correct live balance. Staff look a member up by phone number, and the member list is long.

Build the counter something so every member’s points balance is always exactly right.

(Build it for any café and any member. Get earning, the tiers and redemption right first, then the lookups.)

User: Each submission is expected to be a working full-stack product. Every solution must include:
- A database (real persistence with a sensible schema).
- REST APIs for the core operations — and the candidate must list these endpoints in the README.
- A usable UI over those APIs.
- User registration and login.
- Search.
- A one-page landing page for the product (what it is, key features, target audience, how it helps, and three features they would build next).
- Pagination and sorting

Submission

The final solution must be a public GitHub repository, with the following three files in the root folder (used for evaluation):
- README.md — how to set up, run and debug the project, plus the list of API endpoints.
- REASONING.md — the thought process behind the solution, including how they tested and fixed issues.
- AI_LOGS.md — the complete conversation with the AI tool, pasted as-is. It must not be modified in any way; any alteration will lead to a deduction of marks.

Assistant: Implemented Cafe Pont as a React/Vite frontend with an Express REST API and SQLite persistence. Added JWT registration/login, member search by name or phone, sorting, pagination, tier-aware purchase earning, atomic redemption, live balance refresh, transaction history, responsive landing/auth UI, and the required README.md and REASONING.md files. Validated the frontend with npm run build and fixed the TypeScript type-only import and CSS syntax errors it exposed.
