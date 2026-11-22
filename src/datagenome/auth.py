import hashlib
import json
import logging
import secrets
import sqlite3
import time
from contextlib import contextmanager
from threading import BoundedSemaphore
from typing import Any, Iterator

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import APIRouter, FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from .ingestion import DatasetError
from .ownership import http_owner
from .store import Store


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


class Credentials(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: str = Field(min_length=3, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$")
    password: str = Field(min_length=12, max_length=256)


class Auth:
    def __init__(
        self, store: Store, secure_cookie: bool = False, registration: bool = True
    ) -> None:
        self.store = store
        self.secure_cookie = secure_cookie
        self.registration = registration
        from .configuration import Settings

        settings = Settings.load()
        self.guest_seconds = settings.guest_seconds
        self.session_seconds = settings.session_seconds
        self.hasher = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=1)
        self.hash_slots = BoundedSemaphore(2)
        self.dummy_hash = self.hasher.hash(secrets.token_urlsafe(32))
        with store.connection() as db:
            db.executescript("""CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY, username TEXT UNIQUE, password_hash TEXT,
                guest INTEGER NOT NULL, expires REAL);
                CREATE TABLE IF NOT EXISTS sessions (
                token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL,
                csrf_hash TEXT NOT NULL, expires REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS project_owners (
                project TEXT PRIMARY KEY, user_id TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS rate_limits (
                bucket TEXT PRIMARY KEY, count INTEGER NOT NULL, reset REAL NOT NULL);""")

    @contextmanager
    def hashing_slot(self) -> Iterator[None]:
        if not self.hash_slots.acquire(blocking=False):
            raise DatasetError(
                "authentication_busy", "Retry authentication shortly.", 429
            )
        try:
            yield
        finally:
            self.hash_slots.release()

    def rate(self, bucket: str, limit: int, period: int = 60) -> None:
        at = time.time()
        with self.store.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("DELETE FROM rate_limits WHERE reset<?", (at,))
            row = db.execute(
                "SELECT count FROM rate_limits WHERE bucket=?", (bucket,)
            ).fetchone()
            if row and row["count"] >= limit:
                raise DatasetError("rate_limited", "Wait before retrying.", 429)
            db.execute(
                "INSERT INTO rate_limits VALUES (?,?,?) ON CONFLICT(bucket) DO UPDATE SET count=count+1",
                (bucket, 1, at + period),
            )

    def user(self, token: str | None) -> dict[str, Any] | None:
        if not token or len(token) > 256:
            return None
        with self.store.connection() as db:
            row = db.execute(
                """SELECT u.id,u.username,u.guest,u.expires AS guest_expires,
                s.csrf_hash,s.expires FROM users u JOIN sessions s ON s.user_id=u.id
                WHERE s.token_hash=?""",
                (digest(token),),
            ).fetchone()
        if (
            row is None
            or row["expires"] <= time.time()
            or (
                row["guest_expires"] is not None and row["guest_expires"] <= time.time()
            )
        ):
            return None
        return dict(row)

    def issue(
        self, user_id: str, guest: bool, prior_token: str | None = None
    ) -> JSONResponse:
        token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        duration = self.guest_seconds if guest else self.session_seconds
        expires = time.time() + duration
        with self.store.connection() as db:
            db.execute("DELETE FROM sessions WHERE expires<=?", (time.time(),))
            if prior_token:
                db.execute(
                    "DELETE FROM sessions WHERE token_hash=?", (digest(prior_token),)
                )
            db.execute(
                "INSERT INTO sessions VALUES (?,?,?,?)",
                (digest(token), user_id, digest(csrf), expires),
            )
        response = JSONResponse(
            {
                "user_id": user_id,
                "guest": guest,
                "csrf_token": csrf,
                "expires_at": expires,
            }
        )
        response.set_cookie(
            "datagenome_session",
            token,
            httponly=True,
            secure=self.secure_cookie,
            samesite="strict",
            max_age=duration,
            path="/",
        )
        return response

    def cleanup(self) -> int:
        with self.store.connection() as db:
            db.execute("DELETE FROM sessions WHERE expires<=?", (time.time(),))
            expired = [
                row["id"]
                for row in db.execute(
                    "SELECT id FROM users WHERE expires IS NOT NULL AND expires<=?",
                    (time.time(),),
                ).fetchall()
            ]
        removed = 0
        for owner in expired:
            if self.delete_owner(owner):
                removed += 1
        return removed

    def delete_owner(self, owner: str) -> bool:
        with self.store.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            projects = [
                row["project"]
                for row in db.execute(
                    "SELECT project FROM project_owners WHERE user_id=?", (owner,)
                )
            ]
            for project in projects:
                db.execute(
                    "UPDATE jobs SET cancel=1,state=CASE WHEN state='queued' THEN 'cancelled' ELSE state END WHERE project=? AND state IN ('queued','running')",
                    (project,),
                )
            running = db.execute(
                """SELECT count(*) FROM jobs WHERE project IN
                (SELECT project FROM project_owners WHERE user_id=?) AND state='running'""",
                (owner,),
            ).fetchone()[0]
            db.execute("DELETE FROM sessions WHERE user_id=?", (owner,))
            if running:
                db.execute(
                    "UPDATE users SET expires=? WHERE id=?", (time.time(), owner)
                )
                return False
            for project in projects:
                db.execute(
                    "DELETE FROM events WHERE job IN (SELECT id FROM jobs WHERE project=?)",
                    (project,),
                )
                db.execute("DELETE FROM jobs WHERE project=?", (project,))
                db.execute(
                    "DELETE FROM artifacts WHERE project=? OR id=?", (project, project)
                )
            db.execute("DELETE FROM project_owners WHERE user_id=?", (owner,))
            db.execute("DELETE FROM users WHERE id=?", (owner,))
        return True


def install_auth(
    app: FastAPI, store: Store, *, secure_cookie: bool, registration: bool
) -> Auth:
    from urllib.parse import urlsplit

    auth = Auth(store, secure_cookie, registration)
    router = APIRouter(prefix="/api/v1/auth")

    @app.middleware("http")
    async def security(request: Request, call_next: Any) -> Any:
        started = time.perf_counter()
        correlation = secrets.token_hex(12)
        owner_token = None
        try:
            if request.url.path.startswith("/api/v1/"):
                ip = request.client.host if request.client else "local"
                auth.rate("request:" + digest(ip), 240)
                length = request.headers.get("content-length")
                if length and (not length.isdecimal() or int(length) > 6_000_000):
                    raise DatasetError(
                        "request_too_large", "Request exceeds the byte budget.", 413
                    )
                origin = request.headers.get("origin")
                if origin:
                    parsed = urlsplit(origin)
                    if parsed.scheme not in {
                        "http",
                        "https",
                    } or parsed.netloc != request.headers.get("host"):
                        raise DatasetError(
                            "origin_rejected",
                            "Cross-origin requests are disabled.",
                            403,
                        )
                public = {
                    "/api/v1/capabilities",
                    "/api/v1/auth/register",
                    "/api/v1/auth/login",
                    "/api/v1/auth/guest",
                }
                if request.url.path not in public:
                    user = auth.user(request.cookies.get("datagenome_session"))
                    if user is None:
                        raise DatasetError(
                            "authentication_required", "Create or renew a session.", 401
                        )
                    if request.method not in {"GET", "HEAD", "OPTIONS"}:
                        csrf = request.headers.get("x-csrf-token", "")
                        if not secrets.compare_digest(digest(csrf), user["csrf_hash"]):
                            raise DatasetError(
                                "csrf_rejected", "Supply the session CSRF token.", 403
                            )
                    request.state.user = user
                    owner_token = http_owner.set(user["id"])
            response = await call_next(request)
        except DatasetError as error:
            response = JSONResponse(
                {"error": {"code": error.code, "message": str(error)}},
                status_code=error.status,
            )
        except Exception:
            response = JSONResponse(
                {
                    "error": {
                        "code": "internal_error",
                        "message": "The request could not be completed.",
                    }
                },
                status_code=500,
            )
        finally:
            if owner_token is not None:
                http_owner.reset(owner_token)
        response.headers["X-Request-ID"] = correlation
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Content-Security-Policy"] = (
            "default-src 'none'; frame-ancestors 'none'"
        )
        response.headers["Cache-Control"] = "no-store"
        response.headers["Referrer-Policy"] = "no-referrer"
        logging.getLogger(__name__).log(
            logging.WARNING if response.status_code >= 400 else logging.INFO,
            json.dumps(
                {
                    "event": "security_rejection"
                    if response.status_code >= 400
                    else "request_complete",
                    "request_id": correlation,
                    "status": response.status_code,
                    "duration_ms": round(1000 * (time.perf_counter() - started), 3),
                }
            ),
        )
        return response

    @router.post("/guest")
    def guest() -> JSONResponse:
        auth.rate("guest", 20, 3600)
        auth.cleanup()
        identifier = secrets.token_hex(16)
        with store.connection() as db:
            db.execute(
                "INSERT INTO users VALUES (?,?,?,1,?)",
                (identifier, None, None, time.time() + auth.guest_seconds),
            )
        return auth.issue(identifier, True)

    @router.post("/register")
    def register(spec: Credentials, request: Request) -> JSONResponse:
        if not auth.registration:
            raise DatasetError(
                "registration_disabled", "Registration is disabled.", 403
            )
        auth.rate("registration", 20, 3600)
        identifier = secrets.token_hex(16)
        with auth.hashing_slot():
            hashed = auth.hasher.hash(spec.password)
        try:
            with store.connection() as db:
                db.execute(
                    "INSERT INTO users VALUES (?,?,?,0,NULL)",
                    (identifier, spec.username.casefold(), hashed),
                )
        except sqlite3.IntegrityError:
            raise DatasetError(
                "account_unavailable", "Account registration could not complete.", 409
            ) from None
        return auth.issue(identifier, False, request.cookies.get("datagenome_session"))

    @router.post("/login")
    def login(spec: Credentials, request: Request) -> JSONResponse:
        ip = request.client.host if request.client else "local"
        auth.rate("login:" + digest(ip), 10, 300)
        auth.rate("account-login:" + digest(spec.username.casefold()), 10, 300)
        with store.connection() as db:
            row = db.execute(
                "SELECT id,password_hash FROM users WHERE username=? AND guest=0",
                (spec.username.casefold(),),
            ).fetchone()
        stored = row["password_hash"] if row else auth.dummy_hash
        try:
            with auth.hashing_slot():
                valid: bool = bool(auth.hasher.verify(stored, spec.password))
        except (VerificationError, InvalidHashError):
            valid = False
        if not valid or row is None:
            raise DatasetError(
                "invalid_credentials", "Invalid username or password.", 401
            )
        return auth.issue(row["id"], False, request.cookies.get("datagenome_session"))

    @router.get("/session")
    def session(request: Request) -> dict[str, Any]:
        user = request.state.user
        return {
            "user_id": user["id"],
            "username": user["username"],
            "guest": bool(user["guest"]),
            "expires_at": user["expires"],
        }

    @router.get("/csrf")
    def csrf_token(request: Request) -> dict[str, str]:
        value = secrets.token_urlsafe(32)
        with store.connection() as db:
            db.execute(
                "UPDATE sessions SET csrf_hash=? WHERE token_hash=?",
                (digest(value), digest(request.cookies["datagenome_session"])),
            )
        return {"csrf_token": value}

    @router.post("/logout")
    def logout(request: Request) -> JSONResponse:
        token = request.cookies.get("datagenome_session", "")
        with store.connection() as db:
            db.execute("DELETE FROM sessions WHERE token_hash=?", (digest(token),))
        response = JSONResponse({"status": "logged_out"})
        response.delete_cookie("datagenome_session", path="/")
        return response

    @router.delete("/account")
    def delete_account(request: Request) -> JSONResponse:
        complete = auth.delete_owner(request.state.user["id"])
        response = JSONResponse(
            {"status": "deleted" if complete else "cancellation_pending"},
            status_code=200 if complete else 202,
        )
        response.delete_cookie("datagenome_session", path="/")
        return response

    app.include_router(router)
    return auth
