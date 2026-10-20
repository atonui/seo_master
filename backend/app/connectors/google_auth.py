import json
import time
from collections.abc import Mapping
from typing import Any

import httpx
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.crypto import decrypt_secret
from app.models.connection import GoogleConnection


GOOGLE_SCOPES = (
    "https://www.googleapis.com/auth/webmasters.readonly",
    "https://www.googleapis.com/auth/analytics.readonly",
)


class GoogleApiError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def _is_quota_response(response: httpx.Response) -> bool:
    if response.status_code != 403:
        return False
    try:
        error = response.json().get("error", {})
        reasons = error.get("errors", []) if isinstance(error, dict) else []
        return any(
            any(word in str(item.get("reason", "")).lower() for word in ("quota", "ratelimit"))
            for item in reasons
            if isinstance(item, dict)
        )
    except (ValueError, AttributeError):
        return False


def is_reconnect_required(error: Mapping[str, object] | str) -> bool:
    """Recognize Google's invalid_grant response as a reconnect condition."""
    if isinstance(error, Mapping):
        return error.get("error") == "invalid_grant"
    try:
        parsed = json.loads(error)
    except (ValueError, TypeError):
        return "invalid_grant" in str(error).lower()
    return isinstance(parsed, Mapping) and parsed.get("error") == "invalid_grant"


def _refresh_access_token(refresh_token: str) -> str:
    settings = get_settings()
    try:
        response = httpx.post(
            "https://oauth2.googleapis.com/token",
            data={
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
            },
            timeout=12.0,
        )
        payload = response.json()
    except httpx.TimeoutException as exc:
        raise GoogleApiError("timeout", "Google token refresh timed out") from exc
    except httpx.RequestError as exc:
        raise GoogleApiError("unavailable", "Google token service could not be reached") from exc
    except ValueError as exc:
        raise GoogleApiError("invalid_response", "Google token service returned invalid JSON") from exc
    if response.status_code >= 400:
        if is_reconnect_required(payload if isinstance(payload, Mapping) else ""):
            raise GoogleApiError("reconnect_required", "Google authorization expired; reconnect the account")
        if response.status_code == 429 or response.status_code >= 500:
            raise GoogleApiError("unavailable", "Google token service is temporarily unavailable")
        raise GoogleApiError("authorization", "Google could not refresh its authorization")
    access_token = payload.get("access_token") if isinstance(payload, dict) else None
    if not isinstance(access_token, str) or not access_token:
        raise GoogleApiError("authorization", "Google did not return an access token")
    return access_token


class GoogleApiClient:
    def __init__(self, db: Session):
        self.db = db
        self._access_token_cache: str | None = None

    def _mark_reconnect_required(self) -> None:
        connection = self.db.get(GoogleConnection, 1)
        if connection is not None and not connection.reconnect_required:
            connection.reconnect_required = True
            self.db.commit()

    def get_access_token(self) -> str:
        if self._access_token_cache:
            return self._access_token_cache
        connection = self.db.get(GoogleConnection, 1)
        if connection is None:
            raise GoogleApiError("not_connected", "Connect the Google account first")
        if connection.reconnect_required:
            raise GoogleApiError("reconnect_required", "Reconnect the Google account to continue")
        try:
            credentials = json.loads(decrypt_secret(connection.encrypted_credentials))
            refresh_token = credentials.get("refresh_token")
            if not isinstance(refresh_token, str) or not refresh_token:
                raise GoogleApiError("reconnect_required", "Reconnect the Google account to continue")
            self._access_token_cache = _refresh_access_token(refresh_token)
            return self._access_token_cache
        except GoogleApiError as exc:
            if exc.code == "reconnect_required":
                self._mark_reconnect_required()
            raise
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            raise GoogleApiError("credentials", "Saved Google credentials could not be read") from exc

    def request_json(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        token = self.get_access_token()
        response: httpx.Response | None = None
        for attempt in range(3):
            try:
                response = httpx.request(
                    method,
                    url,
                    params=params,
                    json=body,
                    headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
                    timeout=12.0,
                )
            except httpx.TimeoutException as exc:
                if attempt == 2:
                    raise GoogleApiError("timeout", "Google request timed out") from exc
                time.sleep(0.25 * (2**attempt))
                continue
            except httpx.RequestError as exc:
                if attempt == 2:
                    raise GoogleApiError("unavailable", "Google could not be reached") from exc
                time.sleep(0.25 * (2**attempt))
                continue
            retryable = response.status_code == 429 or response.status_code >= 500 or _is_quota_response(response)
            if retryable and attempt < 2:
                retry_after = response.headers.get("Retry-After", "")
                try:
                    delay = min(max(float(retry_after), 0.0), 2.0) if retry_after else 0.25 * (2**attempt)
                except ValueError:
                    delay = 0.25 * (2**attempt)
                time.sleep(delay)
                continue
            break

        if response is None:
            raise GoogleApiError("unavailable", "Google could not be reached")

        if response.status_code >= 400:
            payload: dict[str, Any] = {}
            try:
                parsed = response.json()
                if isinstance(parsed, dict):
                    payload = parsed
            except ValueError:
                pass
            error = payload.get("error", {})
            reasons = []
            if isinstance(error, dict):
                reasons.extend(
                    str(item.get("reason", ""))
                    for item in error.get("errors", [])
                    if isinstance(item, dict)
                )
            reason_text = " ".join(reasons).lower()
            if response.status_code == 401:
                self._mark_reconnect_required()
                raise GoogleApiError("reconnect_required", "Google authorization expired; reconnect the account")
            if response.status_code == 429 or any(word in reason_text for word in ("quota", "ratelimit")):
                raise GoogleApiError("quota", "Google API quota or rate limit was reached")
            if response.status_code == 403:
                raise GoogleApiError("permission", "Google denied access to this property")
            if response.status_code >= 500:
                raise GoogleApiError("unavailable", "Google API is temporarily unavailable")
            raise GoogleApiError("api_error", "Google API rejected the reporting request")

        try:
            parsed = response.json()
        except ValueError as exc:
            raise GoogleApiError("invalid_response", "Google API returned invalid JSON") from exc
        if not isinstance(parsed, dict):
            raise GoogleApiError("invalid_response", "Google API returned an unexpected response")
        return parsed
