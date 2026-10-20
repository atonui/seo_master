# Sparestracker Marketing Agent

A private, single-owner SEO and marketing analysis workspace for Sparestracker. The agent will read Search Console and GA4 reports, audit the public website, and produce recommendations linked to their evidence. It will not edit or publish site content.

## Current status

The private owner login, Google reporting connectors, safe website crawler, evidence-linked analysis, saved reports, weekly job, and dashboard are implemented. App Store Connect and Google Play reporting are a later integration phase after the app listings are available and the required reports are confirmed.

## Local development

Backend (Python 3.12+ and uv):

```sh
cd backend
uv sync --extra dev
uv run alembic upgrade head
uv run uvicorn app.main:app --reload --no-access-log
```

Frontend (Node 20+):

```sh
cd frontend
npm install
npm run dev
```

Vite proxies `/api` calls to the local FastAPI server on port 8000.

## Deployment

See [the private Railway deployment guide](docs/setup/deployment.md) and [the report validation checklist](docs/setup/report-validation.md). Production requires a PostgreSQL URL, Google OAuth secrets, an OpenAI API key, and an owner email.
