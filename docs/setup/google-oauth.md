# Google OAuth setup

This app uses Google OAuth for one owner account. It asks for OpenID identity and read-only Search Console and Google Analytics access. It does not request write scopes.

## Google Cloud setup

1. Create or select a Google Cloud project and enable the Search Console API, Google Analytics Data API, and Google Analytics Admin API.
2. Configure the OAuth consent screen as **External** for an individual Google account, add the owner as a test user, and register the app name and support email.
3. Create an OAuth client ID for a **Web application**. Add the local callback `http://localhost:8000/api/auth/google/callback` as an authorized redirect URI. Add the production callback after deployment.
4. Put the client ID, client secret, and exact callback URL in the local environment or deployment secret manager. Do not commit them.

The requested scopes are `openid`, `email`, `profile`, `https://www.googleapis.com/auth/webmasters.readonly`, and `https://www.googleapis.com/auth/analytics.readonly`. The owner must already have access to the Search Console site and GA4 property.

## Local keys

Generate a session signing key with `python -c 'import secrets; print(secrets.token_urlsafe(48))'`. Generate the Fernet encryption key with `uv run python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'`. Store each value in an ignored `.env` file or a secret manager.

For local work, copy `backend/.env.example` to `backend/.env` and fill in the owner email, generated keys, OAuth client values, and callback URL.

Run the database migration before starting the app:

```sh
cd backend
uv run alembic upgrade head
uv run uvicorn app.main:app --reload
```

Open the app and call `GET /api/auth/google/start` to begin authorization. Google will redirect back to the configured callback. The app checks the OAuth state, OpenID nonce, token issuer and audience, verified email, and owner allowlist before creating a session.

Google OAuth apps left in **Testing** can issue refresh tokens that expire after seven days. Check the OAuth publishing status and any scope verification requirements before enabling unattended weekly reporting. If Google returns `invalid_grant`, the app must mark the connection as requiring a reconnect and retain the last successful report.
