"""Authentication for all p15 services: bcrypt passwords, JWT + server sessions.

Lab 1 issued a stateless 30-minute JWT. Lab 2 keeps the same bearer token
for the frontend but ties every token to a row in the `sessions`
collection:

  * login creates {_id: sid, user_id, created_at, expires_at}
  * the JWT carries that sid; every request checks the session still exists
    and has not expired, so logout (or an admin) can revoke a token early
  * a TTL index on expires_at makes MongoDB delete expired sessions itself

Passwords are bcrypt hashes, unchanged from Lab 1 (the migration copies the
hashes, so existing accounts keep working).
"""
import os
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from passlib.context import CryptContext

from services.common.mongo import (
    SESSION_TTL_MINUTES, SESSIONS, USERS, get_mongo, log_activity, utcnow)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
bearer = HTTPBearer(auto_error=False)
ALGORITHM = "HS256"


def secret_key() -> str:
    key = os.getenv("JWT_SECRET_KEY", "")
    if len(key) < 32:
        raise RuntimeError("Set JWT_SECRET_KEY to a random secret of at least 32 characters")
    return key


@dataclass
class CurrentUser:
    id: int
    email: str
    role: str
    is_active: bool
    created_at: datetime
    session_id: str | None = None

    @classmethod
    def from_doc(cls, doc, session_id=None):
        return cls(id=doc["_id"], email=doc["email"], role=doc["role"],
                   is_active=doc.get("is_active", True),
                   created_at=doc["created_at"], session_id=session_id)


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return pwd_context.verify(password, password_hash)
    except (ValueError, TypeError):
        return False


def start_session(db, user_doc, client_info: str | None = None) -> str:
    """Create a server-side session and return the signed JWT for it."""
    now = utcnow()
    sid = secrets.token_urlsafe(24)
    expires = now + timedelta(minutes=SESSION_TTL_MINUTES)
    db[SESSIONS].insert_one({"_id": sid, "user_id": user_doc["_id"],
                             "role": user_doc["role"], "created_at": now,
                             "expires_at": expires, "client": client_info})
    log_activity(db, user_doc["_id"], "login", session_id=sid)
    issued = datetime.now(timezone.utc)
    return jwt.encode({"sub": str(user_doc["_id"]), "role": user_doc["role"],
                       "sid": sid, "iat": issued,
                       "exp": issued + timedelta(minutes=SESSION_TTL_MINUTES)},
                      secret_key(), algorithm=ALGORITHM)


def end_session(db, user: "CurrentUser") -> None:
    if user.session_id:
        db[SESSIONS].delete_one({"_id": user.session_id, "user_id": user.id})
        log_activity(db, user.id, "logout", session_id=user.session_id)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db=Depends(get_mongo),
) -> CurrentUser:
    unauthorized = HTTPException(
        status_code=401, detail="Invalid or expired authentication",
        headers={"WWW-Authenticate": "Bearer"})
    if credentials is None:
        raise unauthorized
    try:
        payload = jwt.decode(credentials.credentials, secret_key(), algorithms=[ALGORITHM],
                             options={"require": ["sub", "role", "sid", "iat", "exp"]})
        user_id = int(payload["sub"])
    except (jwt.InvalidTokenError, ValueError, TypeError):
        raise unauthorized
    session = db[SESSIONS].find_one({"_id": payload["sid"], "user_id": user_id,
                                     "expires_at": {"$gt": utcnow()}})
    if session is None:
        raise unauthorized
    doc = db[USERS].find_one({"_id": user_id})
    if doc is None or not doc.get("is_active", True) or payload["role"] != doc["role"]:
        raise unauthorized
    return CurrentUser.from_doc(doc, session_id=payload["sid"])


def require_role(role: str):
    def check_role(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if user.role != role:
            raise HTTPException(status_code=403, detail=f"{role.title()} account required")
        return user
    return check_role


require_student = require_role("student")
require_company = require_role("company")
