# Private Railway deployment

This app is a single-owner workspace. Google OAuth restricts access to `OWNER_EMAIL`; the production session cookie is HTTP-only, SameSite=Lax, and Secure. The public health route contains no account or report data. No content is published or changed by the agent.

## Services

Create a Railway project with a PostgreSQL service and two services built from the repository root `Dockerfile`:

1. **Web** uses the Dockerfile default command, which upgrades the database to the current Alembic revision and starts FastAPI. Generate a Railway domain or attach a private custom hostname, then set `PUBLIC_BASE_URL` to its HTTPS origin.
2. **Weekly report** uses the same image, with start command `uv run python -m app.jobs.weekly_report` and cron schedule `0 5 * * 1`. Railway cron schedules use UTC; this runs Monday at 08:00 in Nairobi. The process exits after one report run and closes the database session. citeturn14search0

Set the cron schedule in the service’s Settings. Do not run a second in-process scheduler. The job is idempotent for a completed week.

## Variables and secrets

Set these in Railway service variables. Share `DATABASE_URL` and the app secrets with both services; `PUBLIC_BASE_URL` and OAuth values are required by the web service. Railway reference variables can point `DATABASE_URL` at the PostgreSQL service.

| Variable | Value |
|---|---|
| `APP_ENV` | `production` |
| `OWNER_EMAIL` | Your exact Google account email |
| `SESSION_SIGNING_KEY` | Random secret of at least 32 characters |
| `TOKEN_ENCRYPTION_KEY` | Fernet key generated with `python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'` |
| `DATABASE_URL` | Railway PostgreSQL connection URL using `postgresql+psycopg://` or `postgresql://` |
| `GOOGLE_CLIENT_ID` | OAuth client ID |
| `GOOGLE_CLIENT_SECRET` | OAuth client secret |
| `GOOGLE_REDIRECT_URI` | Exactly `${PUBLIC_BASE_URL}/api/auth/google/callback` |
| `PUBLIC_BASE_URL` | Public HTTPS origin, without a path |
| `OPENAI_API_KEY` | OpenAI API key for structured recommendations and chat |
| `OPENAI_MODEL` | `gpt-4.1-mini` unless you intentionally configure another supported model |

Generate a signing secret with `python -c 'import secrets; print(secrets.token_urlsafe(48))'`. Enter credentials only in Railway’s secret variable controls. Do not put them in this repository or the image.

Configure the Google OAuth consent screen as External or Internal according to the owner account. Add the owner as a test user while the consent screen is in Testing. Add the exact callback URL as an authorized redirect URI. Before unattended weekly use, verify the OAuth app’s publishing status and refresh-token lifetime. Keep the scopes read-only.

Production startup fails early if required secrets are missing, the redirect URI does not match, the public URL is not HTTPS, or the database URL is not PostgreSQL. The default web start command applies Alembic migrations before serving requests. Health check path: `/api/health`.

## Local image check

From the repository root, build with `docker build -t sparestracker-marketing-agent .`. For a local run, pass the values from `backend/.env.example`; the production checks are skipped when `APP_ENV` is not `production`. The Docker image serves the built React app and API from one origin.

## Current deployment status

This repository contains deployment packaging and checks. No Railway service has been created from this workspace yet. The external Google and OpenAI credentials must be entered as deployment secrets before a report can run.
