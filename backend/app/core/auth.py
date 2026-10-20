import base64
import hashlib
import hmac
import time

from fastapi import Cookie, HTTPException

from app.core.config import Settings, get_settings

SESSION_COOKIE = "owner_session"
SESSION_MAX_AGE = 14 * 24 * 60 * 60


def make_session(email: str, signing_key: str, now: int | None = None) -> str:
    if not signing_key:
        raise RuntimeError("SESSION_SIGNING_KEY is required for owner sessions")
    expiry = (now or int(time.time())) + SESSION_MAX_AGE
    payload = f"{email.casefold()}|{expiry}".encode("utf-8")
    encoded = base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")
    signature = hmac.new(signing_key.encode("utf-8"), encoded.encode("ascii"), hashlib.sha256).hexdigest()
    return f"{encoded}.{signature}"


def session_email(cookie: str, settings: Settings, now: int | None = None) -> str | None:
    if not settings.session_signing_key:
        return None
    try:
        encoded, signature = cookie.rsplit(".", 1)
        expected = hmac.new(settings.session_signing_key.encode("utf-8"), encoded.encode("ascii"), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected):
            return None
        padded = encoded + "=" * (-len(encoded) % 4)
        email, expiry_text = base64.urlsafe_b64decode(padded).decode("utf-8").rsplit("|", 1)
        if int(expiry_text) <= (now or int(time.time())) or email.casefold() != settings.owner_email:
            return None
        return email
    except (ValueError, UnicodeDecodeError, TypeError):
        return None


def require_owner(owner_session: str | None = Cookie(default=None, alias=SESSION_COOKIE)) -> str:
    email = session_email(owner_session or "", get_settings())
    if not email:
        raise HTTPException(status_code=401, detail="Owner login required")
    return email
