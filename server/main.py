import json
import os
import sqlite3
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Annotated

import bcrypt
import jwt
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = Path(os.getenv("DATABASE_PATH", Path(__file__).resolve().parent / "cafe-pont.db"))
JWT_SECRET = os.getenv("JWT_SECRET", "cafe-pont-local-secret")
PORT = int(os.getenv("PORT", "3001"))


class Credentials(BaseModel):
    email: str
    password: str


class Purchase(BaseModel):
    amount: float = Field(gt=0)


class Redemption(BaseModel):
    points: int = Field(gt=0)
    rewardName: str = "Free drink"


class ClockRequest(BaseModel):
    now: datetime | None = None
    advanceDays: int | None = None
    advance_days: int | None = None


def connect() -> sqlite3.Connection:
    connection = sqlite3.connect(DB_PATH, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode = WAL")
    return connection


def setup_database() -> None:
    with connect() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, email TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS members (id INTEGER PRIMARY KEY, name TEXT NOT NULL, phone TEXT UNIQUE NOT NULL, points INTEGER NOT NULL DEFAULT 0, lifetime_spend_cents INTEGER NOT NULL DEFAULT 0, lifetime_points_earned INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS transactions (id INTEGER PRIMARY KEY, member_id INTEGER NOT NULL REFERENCES members(id), type TEXT NOT NULL CHECK(type IN ('purchase', 'redemption')), amount_cents INTEGER, points_delta INTEGER NOT NULL, reward_name TEXT, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS point_lots (id INTEGER PRIMARY KEY, member_id INTEGER NOT NULL REFERENCES members(id), transaction_id INTEGER REFERENCES transactions(id), granted_points INTEGER NOT NULL, remaining_points INTEGER NOT NULL, earned_at TEXT NOT NULL, expired_at TEXT);
        CREATE TABLE IF NOT EXISTS notifications_outbox (id INTEGER PRIMARY KEY, member_id INTEGER NOT NULL REFERENCES members(id), event_type TEXT NOT NULL, payload TEXT NOT NULL, created_at TEXT NOT NULL, delivered_at TEXT);
        """)
        member_columns = {row["name"] for row in db.execute("PRAGMA table_info(members)").fetchall()}
        if "lifetime_points_earned" not in member_columns:
            db.execute("ALTER TABLE members ADD COLUMN lifetime_points_earned INTEGER NOT NULL DEFAULT 0")
        if db.execute("SELECT COUNT(*) FROM members").fetchone()[0] == 0:
            db.executemany(
                "INSERT INTO members (name, phone, points, lifetime_spend_cents, lifetime_points_earned) VALUES (?, ?, ?, ?, ?)",
                [
                    ("Maya Chen", "415-555-0138", 2380, 238000, 2380),
                    ("Theo Grant", "415-555-0172", 1240, 124000, 1240),
                    ("Rina Patel", "415-555-0191", 760, 76000, 760),
                    ("Jon Bell", "415-555-0114", 410, 41000, 410),
                    ("Ava Williams", "415-555-0155", 1840, 184000, 1840),
                    ("Nico Santos", "415-555-0184", 320, 32000, 320),
                ],
            )
        db.execute("UPDATE members SET lifetime_points_earned = points WHERE lifetime_points_earned = 0 AND points > 0")
        # Backfill pre-existing balances as one lot so they participate in expiration.
        db.execute("""
            INSERT INTO point_lots (member_id, granted_points, remaining_points, earned_at)
            SELECT m.id, m.points, m.points, m.created_at
            FROM members m
            WHERE m.points > 0 AND NOT EXISTS (
                SELECT 1 FROM point_lots l WHERE l.member_id = m.id
            )
        """)


PLATINUM_LIFETIME_POINTS = 5_000


def tier_for(points: int, lifetime_points_earned: int = 0) -> dict:
    if lifetime_points_earned >= PLATINUM_LIFETIME_POINTS:
        return {"name": "Platinum", "multiplier": 0.3, "next": None}
    if points >= 2000:
        return {"name": "Gold", "multiplier": 2, "next": None}
    if points >= 500:
        return {"name": "Silver", "multiplier": 1.5, "next": 2000}
    return {"name": "Regular", "multiplier": 1, "next": 500}


def public_member(member: sqlite3.Row | None) -> dict | None:
    if member is None:
        return None
    result = dict(member)
    result["tier"] = tier_for(result["points"], result["lifetime_points_earned"])
    result["balance"] = result["points"] / 100
    return result


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def check_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode(), password_hash.encode())


def token_for(user_id: int, email: str) -> str:
    return jwt.encode({"id": user_id, "email": email}, JWT_SECRET, algorithm="HS256")


def current_user(authorization: Annotated[str | None, Header()] = None) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Please log in to continue.")
    try:
        return jwt.decode(authorization.removeprefix("Bearer "), JWT_SECRET, algorithms=["HS256"])
    except jwt.InvalidTokenError as error:
        raise HTTPException(401, "Please log in to continue.") from error


def points_for_purchase(cents: int, tier: dict) -> int:
    if tier["name"] == "Platinum":
        return cents * 3 // 1000
    if tier["name"] == "Gold":
        return cents * 2 // 100
    if tier["name"] == "Silver":
        return cents * 3 // 200
    return cents // 100


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def timestamp(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).replace(tzinfo=None).isoformat(timespec="seconds")


def notify_tier_change(db: sqlite3.Connection, member: sqlite3.Row, before: dict, after: dict, created_at: str) -> None:
    if before["name"] == after["name"]:
        return
    payload = {
        "memberId": member["id"],
        "memberName": member["name"],
        "fromTier": before["name"],
        "toTier": after["name"],
    }
    db.execute(
        "INSERT INTO notifications_outbox (member_id, event_type, payload, created_at) VALUES (?, 'tier.changed', ?, ?)",
        (member["id"], json.dumps(payload), created_at),
    )


def expire_points(db: sqlite3.Connection, as_of: datetime) -> int:
    cutoff = as_of - timedelta(days=90)
    cutoff_text = timestamp(cutoff)
    expired_total = 0
    stale_lots = db.execute(
        "SELECT * FROM point_lots WHERE remaining_points > 0 AND earned_at <= ? ORDER BY earned_at, id",
        (cutoff_text,),
    ).fetchall()
    for lot in stale_lots:
        expired = lot["remaining_points"]
        if expired <= 0:
            continue
        created_at = timestamp(as_of)
        db.execute(
            "INSERT INTO transactions (member_id, type, points_delta, reward_name, created_at) VALUES (?, 'redemption', ?, 'Expired points (90 days)', ?)",
            (lot["member_id"], -expired, created_at),
        )
        db.execute("UPDATE point_lots SET remaining_points = 0, expired_at = ? WHERE id = ?", (created_at, lot["id"]))
        db.execute("UPDATE members SET points = MAX(points - ?, 0) WHERE id = ?", (expired, lot["member_id"]))
        expired_total += expired
    return expired_total


@asynccontextmanager
async def lifespan(_app: FastAPI):
    setup_database()
    yield


app = FastAPI(title="Cafe Pont API", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.exception_handler(HTTPException)
async def http_error(_request: Request, exception: HTTPException):
    return JSONResponse(status_code=exception.status_code, content={"error": str(exception.detail)})


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, _exception: RequestValidationError):
    if request.url.path.endswith("/purchase"):
        message = "Enter a purchase amount greater than zero."
    elif request.url.path.endswith("/redeem"):
        message = "Enter whole points greater than zero."
    else:
        message = "Please check the submitted values."
    return JSONResponse(status_code=422, content={"error": message})


@app.post("/api/auth/register", status_code=201)
def register(credentials: Credentials):
    if len(credentials.password) < 6:
        raise HTTPException(400, "Email and a 6+ character password are required.")
    email = credentials.email.lower()
    try:
        with connect() as db:
            result = db.execute("INSERT INTO users (email, password_hash) VALUES (?, ?)", (email, hash_password(credentials.password)))
            user_id = result.lastrowid
    except sqlite3.IntegrityError as error:
        raise HTTPException(409, "That email is already registered.") from error
    return {"token": token_for(user_id, email), "email": email}


@app.post("/api/auth/login")
def login(credentials: Credentials):
    with connect() as db:
        user = db.execute("SELECT * FROM users WHERE email = ?", (credentials.email.lower(),)).fetchone()
    if user is None or not check_password(credentials.password, user["password_hash"]):
        raise HTTPException(401, "Invalid email or password.")
    return {"token": token_for(user["id"], user["email"]), "email": user["email"]}


@app.get("/api/members")
def list_members(
    _user: Annotated[dict, Depends(current_user)],
    search: str = "",
    sort: str = Query("points", pattern="^(name|points|lifetime_spend_cents)$"),
    direction: str = Query("desc", pattern="^(asc|desc)$"),
    page: int = Query(1, ge=1),
    limit: int = Query(5, ge=1, le=50),
):
    where = "WHERE name LIKE ? OR phone LIKE ?" if search.strip() else ""
    params: list = [f"%{search.strip()}%", f"%{search.strip()}%"] if where else []
    order = "ASC" if direction == "asc" else "DESC"
    with connect() as db:
        total = db.execute(f"SELECT COUNT(*) FROM members {where}", params).fetchone()[0]
        rows = db.execute(f"SELECT * FROM members {where} ORDER BY {sort} {order} LIMIT ? OFFSET ?", (*params, limit, (page - 1) * limit)).fetchall()
    return {"members": [public_member(row) for row in rows], "page": page, "limit": limit, "total": total, "pages": max(1, (total + limit - 1) // limit)}


def member_or_404(db: sqlite3.Connection, member_id: int) -> sqlite3.Row:
    member = db.execute("SELECT * FROM members WHERE id = ?", (member_id,)).fetchone()
    if member is None:
        raise HTTPException(404, "Member not found.")
    return member


@app.get("/api/members/{member_id}")
def get_member(member_id: int, _user: Annotated[dict, Depends(current_user)]):
    with connect() as db:
        member = member_or_404(db, member_id)
        transactions = db.execute("SELECT * FROM transactions WHERE member_id = ? ORDER BY created_at DESC LIMIT 12", (member_id,)).fetchall()
    return {"member": public_member(member), "transactions": [dict(row) for row in transactions]}


@app.post("/api/members/{member_id}/purchase", status_code=201)
def purchase(member_id: int, purchase_data: Purchase, _user: Annotated[dict, Depends(current_user)]):
    cents = round(purchase_data.amount * 100)
    with connect() as db:
        member = member_or_404(db, member_id)
        before_tier = tier_for(member["points"], member["lifetime_points_earned"])
        points = points_for_purchase(cents, before_tier)
        created_at = timestamp(utc_now())
        db.execute("UPDATE members SET points = points + ?, lifetime_spend_cents = lifetime_spend_cents + ?, lifetime_points_earned = lifetime_points_earned + ? WHERE id = ?", (points, cents, points, member_id))
        transaction = db.execute(
            "INSERT INTO transactions (member_id, type, amount_cents, points_delta, created_at) VALUES (?, 'purchase', ?, ?, ?)",
            (member_id, cents, points, created_at),
        )
        db.execute(
            "INSERT INTO point_lots (member_id, transaction_id, granted_points, remaining_points, earned_at) VALUES (?, ?, ?, ?, ?)",
            (member_id, transaction.lastrowid, points, points, created_at),
        )
        updated = member_or_404(db, member_id)
        notify_tier_change(db, updated, before_tier, tier_for(updated["points"], updated["lifetime_points_earned"]), created_at)
    return {"member": public_member(updated), "pointsAdded": points}


@app.post("/api/members/{member_id}/redeem", status_code=201)
def redeem(member_id: int, redemption: Redemption, _user: Annotated[dict, Depends(current_user)]):
    with connect() as db:
        member = member_or_404(db, member_id)
        if redemption.points > member["points"]:
            raise HTTPException(400, "Not enough points for this redemption.")
        created_at = timestamp(utc_now())
        db.execute("UPDATE members SET points = points - ? WHERE id = ?", (redemption.points, member_id))
        db.execute(
            "INSERT INTO transactions (member_id, type, points_delta, reward_name, created_at) VALUES (?, 'redemption', ?, ?, ?)",
            (member_id, -redemption.points, redemption.rewardName.strip() or "Free drink", created_at),
        )
        remaining = redemption.points
        lots = db.execute(
            "SELECT id, remaining_points FROM point_lots WHERE member_id = ? AND remaining_points > 0 ORDER BY earned_at, id",
            (member_id,),
        ).fetchall()
        for lot in lots:
            used = min(remaining, lot["remaining_points"])
            db.execute("UPDATE point_lots SET remaining_points = remaining_points - ? WHERE id = ?", (used, lot["id"]))
            remaining -= used
            if remaining == 0:
                break
        updated = member_or_404(db, member_id)
    return {"member": public_member(updated), "pointsUsed": redemption.points}


@app.post("/clock")
@app.post("/api/clock")
def clock(clock_request: ClockRequest = ClockRequest()):
    advance_days = clock_request.advanceDays if clock_request.advanceDays is not None else clock_request.advance_days
    as_of = clock_request.now or utc_now()
    if advance_days is not None:
        as_of = as_of + timedelta(days=advance_days)
    if as_of.tzinfo is None:
        as_of = as_of.replace(tzinfo=timezone.utc)
    as_of = as_of.astimezone(timezone.utc).replace(tzinfo=None)
    with connect() as db:
        expired_points = expire_points(db, as_of)
    return {"now": timestamp(as_of), "expiredPoints": expired_points}


@app.get("/outbox")
@app.get("/api/outbox")
@app.post("/outbox")
@app.post("/api/outbox")
def outbox():
    with connect() as db:
        rows = db.execute("SELECT * FROM notifications_outbox ORDER BY id").fetchall()
    return [{**dict(row), "payload": json.loads(row["payload"])} for row in rows]


@app.get("/api/health")
def health():
    return {"status": "ok"}


dist_index = BASE_DIR / "dist" / "index.html"
if (BASE_DIR / "dist").exists():
    app.mount("/assets", StaticFiles(directory=BASE_DIR / "dist" / "assets"), name="assets")


@app.get("/{path:path}")
def frontend(path: str):
    if path.startswith("api/") or not dist_index.exists():
        raise HTTPException(404, "Not found")
    return FileResponse(dist_index)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=PORT)