"""Lightweight RBAC authentication and session tokens for SentinelDesk."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import threading
import time
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

Role = Literal["user", "admin"]


class UserRecord(BaseModel):
    email: str
    name: str
    role: Role
    password_hash: str
    salt: str


class PublicUser(BaseModel):
    email: str
    name: str
    role: Role


_SECRET = os.environ.get("SENTINEL_AUTH_SECRET", "sentineldesk-dev-secret-key").encode("utf-8")
_TOKEN_TTL_SECONDS = 60 * 60 * 12  # 12 hours
USERS_PATH = Path(os.environ.get("SENTINEL_USERS_PATH", "data/sentinel/users.json"))
_lock = threading.Lock()
_users: dict[str, UserRecord] = {}


def _load_users() -> None:
    if _users:
        return
    if USERS_PATH.exists():
        try:
            raw = json.loads(USERS_PATH.read_text(encoding="utf-8"))
            for item in raw:
                rec = UserRecord.model_validate(item)
                _users[rec.email] = rec
        except (OSError, ValueError, json.JSONDecodeError):
            pass
    _seed_demo_users()


def _save_users() -> None:
    try:
        USERS_PATH.parent.mkdir(parents=True, exist_ok=True)
        USERS_PATH.write_text(
            json.dumps([u.model_dump() for u in _users.values()], indent=2),
            encoding="utf-8",
        )
    except OSError:
        pass


def _hash_password(password: str, salt: str) -> str:
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 100_000)
    return base64.b64encode(dk).decode("ascii")


def _seed_demo_users() -> None:
    changed = False
    for email, name, role, pwd in (
        ("user@sentineldesk.local", "Dr. Weber", "user", "user123"),
        ("admin@sentineldesk.local", "Admin Ops", "admin", "admin123"),
    ):
        if email not in _users:
            salt = secrets.token_hex(16)
            _users[email] = UserRecord(
                email=email,
                name=name,
                role=role,  # type: ignore[arg-type]
                password_hash=_hash_password(pwd, salt),
                salt=salt,
            )
            changed = True
    if changed:
        _save_users()


def register_user(name: str, email: str, password: str, role: Role) -> PublicUser:
    clean_email = email.strip().lower()
    if not clean_email or "@" not in clean_email:
        raise ValueError("Valid email is required")
    if len(password) < 4:
        raise ValueError("Password must be at least 4 characters")
    with _lock:
        _load_users()
        if clean_email in _users:
            raise ValueError("An account with this email already exists")
        salt = secrets.token_hex(16)
        rec = UserRecord(
            email=clean_email,
            name=name.strip() or clean_email.split("@")[0],
            role=role,
            password_hash=_hash_password(password, salt),
            salt=salt,
        )
        _users[clean_email] = rec
        _save_users()
        return PublicUser(email=rec.email, name=rec.name, role=rec.role)


def authenticate_user(email: str, password: str) -> PublicUser | None:
    clean_email = email.strip().lower()
    with _lock:
        _load_users()
        rec = _users.get(clean_email)
    if rec is None:
        return None
    candidate = _hash_password(password, rec.salt)
    if not hmac.compare_digest(candidate, rec.password_hash):
        return None
    return PublicUser(email=rec.email, name=rec.name, role=rec.role)


def issue_token(user: PublicUser) -> str:
    payload = json.dumps(
        {"email": user.email, "name": user.name, "role": user.role, "exp": int(time.time()) + _TOKEN_TTL_SECONDS},
        separators=(",", ":"),
    ).encode("utf-8")
    b64 = base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")
    sig = hmac.new(_SECRET, b64.encode("ascii"), hashlib.sha256).hexdigest()
    return f"{b64}.{sig}"


def verify_token(token: str) -> PublicUser | None:
    if "." not in token:
        return None
    b64, sig = token.split(".", 1)
    expected = hmac.new(_SECRET, b64.encode("ascii"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, expected):
        return None
    try:
        padded = b64 + "=" * (-len(b64) % 4)
        data = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8"))
        if int(data.get("exp", 0)) < int(time.time()):
            return None
        return PublicUser(email=data["email"], name=data["name"], role=data["role"])
    except (ValueError, KeyError, json.JSONDecodeError):
        return None


def reset_users() -> None:
    with _lock:
        _users.clear()
        _seed_demo_users()
