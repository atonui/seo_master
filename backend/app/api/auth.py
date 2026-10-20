import hmac
import json
import secrets
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from google.auth.transport.requests import Request as GoogleRequest
from google.oauth2 import id_token
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.auth import SESSION_COOKIE, SESSION_MAX_AGE, make_session, require_owner
from app.core.crypto import encrypt_secret
from app.db import get_db
from app.models.connection import GoogleConnection


router = APIRouter(prefix="/api/auth", tags=["authentication"])
GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_SCOPES = (
    "openid",
    "email",
    "profile",
    "https://www.googleapis.com/auth/webmasters.readonly",
    "https://www.googleapis.com/auth/analytics.readonly",
)
COOKIE_PATH = "/api/auth/google"
STATE_COOKIE = "oauth_state"
NONCE_COOKIE = "oauth_nonce"


def _require_oauth_settings(settings: Settings) -> None:
    if not settings.google_client_id or not settings.google_client_secret or not settings.google_redirect_uri:
        raise HTTPException(status_code=503, detail="Google OAuth is not configured")
    if not settings.owner_email or not settings.session_signing_key or not settings.token_encryption_key:
        raise HTTPException(status_code=503, detail="Owner login and credential encryption are not configured")
    try:
        encrypt_secret("configuration-check")
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail="Credential encryption key is invalid") from exc


def exchange_code(code: str) -> dict[str, object]:
    settings = get_settings()
    _require_oauth_settings(settings)
    try:
        response = httpx.post(
            GOOGLE_TOKEN_URL,
            data={
                "code": code,
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "redirect_uri": settings.google_redirect_uri,
                "grant_type": "authorization_code",
            },
            timeout=10.0,
        )
        response.raise_for_status()
        token_data = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(status_code=502, detail="Google authorization could not be completed") from exc
    if not isinstance(token_data, dict) or not isinstance(token_data.get("id_token"), str):
        raise HTTPException(status_code=502, detail="Google authorization response was incomplete")
    return token_data


def verify_id_token(token: str, nonce: str) -> dict[str, object]:
    settings = get_settings()
    try:
        claims = id_token.verify_oauth2_token(token, GoogleRequest(), settings.google_client_id)
    except Exception as exc:
        raise ValueError("Google ID token validation failed") from exc
    if claims.get("iss") not in {"accounts.google.com", "https://accounts.google.com"}:
        raise ValueError("Unexpected Google token issuer")
    if claims.get("aud") != settings.google_client_id:
        raise ValueError("Unexpected Google token audience")
    if not hmac.compare_digest(str(claims.get("nonce", "")), nonce):
        raise ValueError("OAuth nonce did not match")
    return claims


@router.get("/google/start")
def google_start(response: Response, settings: Settings = Depends(get_settings)) -> dict[str, str]:
    _require_oauth_settings(settings)
    state = secrets.token_urlsafe(32)
    nonce = secrets.token_urlsafe(32)
    query = urlencode({
        "client_id": settings.google_client_id,
        "redirect_uri": settings.google_redirect_uri,
        "response_type": "code",
        "scope": " ".join(GOOGLE_SCOPES),
        "access_type": "offline",
        "prompt": "consent",
        "include_granted_scopes": "true",
        "state": state,
        "nonce": nonce,
    })
    secure = settings.environment == "production"
    for name, value in ((STATE_COOKIE, state), (NONCE_COOKIE, nonce)):
        response.set_cookie(name, value, max_age=600, httponly=True, secure=secure, samesite="lax", path=COOKIE_PATH)
    return {"authorization_url": f"{GOOGLE_AUTH_URL}?{query}"}


@router.get("/google/callback")
def google_callback(
    code: str,
    state: str,
    request: Request,
    settings: Settings = Depends(get_settings),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    saved_state = request.cookies.get(STATE_COOKIE, "")
    nonce = request.cookies.get(NONCE_COOKIE, "")
    if not saved_state or not hmac.compare_digest(state, saved_state) or not nonce:
        raise HTTPException(status_code=400, detail="OAuth state validation failed")

    token_data = exchange_code(code)
    raw_id_token = token_data.get("id_token")
    if not isinstance(raw_id_token, str):
        raise HTTPException(status_code=400, detail="Google did not return an identity token")
    try:
        claims = verify_id_token(raw_id_token, nonce)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Google identity validation failed") from exc
    email = str(claims.get("email", "")).strip().casefold()
    if not claims.get("email_verified") or not settings.owner_email or not hmac.compare_digest(email, settings.owner_email):
        raise HTTPException(status_code=403, detail="This account is not authorized to access the private workspace")

    refresh_token = token_data.get("refresh_token")
    existing = db.get(GoogleConnection, 1)
    if not isinstance(refresh_token, str) or not refresh_token:
        if existing is None:
            raise HTTPException(status_code=400, detail="Google did not issue a refresh token; start again and grant offline access")
        from app.core.crypto import decrypt_secret

        old_credentials = json.loads(decrypt_secret(existing.encrypted_credentials))
        refresh_token = old_credentials.get("refresh_token")
        if not refresh_token:
            raise HTTPException(status_code=400, detail="Google did not issue a refresh token; reconnect with offline access")
    encrypted = encrypt_secret(json.dumps({"refresh_token": refresh_token}, separators=(",", ":")))
    if existing is None:
        existing = GoogleConnection(owner_email=email, encrypted_credentials=encrypted, reconnect_required=False)
        db.add(existing)
    else:
        existing.encrypted_credentials = encrypted
        existing.reconnect_required = False
    db.commit()

    redirect = RedirectResponse(url="/", status_code=303)
    secure = settings.environment == "production"
    redirect.set_cookie(
        SESSION_COOKIE,
        make_session(email, settings.session_signing_key),
        max_age=SESSION_MAX_AGE,
        httponly=True,
        secure=secure,
        samesite="lax",
        path="/",
    )
    redirect.delete_cookie(STATE_COOKIE, path=COOKIE_PATH)
    redirect.delete_cookie(NONCE_COOKIE, path=COOKIE_PATH)
    return redirect


@router.get("/me")
def current_owner(email: str = Depends(require_owner)) -> dict[str, str]:
    return {"email": email}


@router.post("/logout", status_code=204)
def logout(response: Response, settings: Settings = Depends(get_settings), _: str = Depends(require_owner)) -> Response:
    response.delete_cookie(SESSION_COOKIE, path="/", secure=settings.environment == "production", httponly=True, samesite="lax")
    response.status_code = 204
    return response
