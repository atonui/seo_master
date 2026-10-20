# Sparestracker Marketing Agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a private, single-owner marketing agent that reads Sparestracker's website, Search Console, and GA4 data and produces evidence-linked SEO and funnel recommendations.

**Architecture:** A FastAPI backend owns login, Google API access, storage, crawling, analysis, and report APIs. A React/TypeScript web client provides property setup, reports, and chat. A separate short-lived Railway Cron service runs the weekly report command against the same PostgreSQL database. Deterministic code computes metrics; an LLM turns selected evidence into structured recommendations. App store sources remain a later phase.

**Tech Stack:** Python, FastAPI, SQLAlchemy, Alembic, PostgreSQL, Google Search Console API, Google Analytics Data/Admin APIs, React, TypeScript, Vite, pytest, Vitest, Playwright, OpenAI API, Railway.

**Spec:** `docs/superpowers/specs/2026-10-20-sparestracker-marketing-agent-design.md`

## Global Constraints

- One authorized user; no customer accounts, multi-tenant abstractions, or external writes in v1.
- Request read-only Google access for Search Console and GA4.
- Do not ingest names, email addresses, form contents, or individual lead records.
- Do not send OAuth tokens, API keys, or personal lead data to the model or logs.
- The model receives relevant aggregates and public crawl findings only.
- Every recommendation includes source evidence, date range, proposed action, measure, and confidence.
- Missing, stale, partial, low-volume, or failed data must be labeled; do not infer a cause from correlation alone.
- The crawler stays on the configured public Sparestracker domain, obeys robots directives, and uses bounded page and request limits.
- No content publishing, website edits, analytics changes, store listing edits, or campaign sending in v1.
- Google Play and App Store Connect are deferred until the apps are published.
- Run the default weekly report on Monday 08:00 Africa/Nairobi (`0 5 * * 1` in Railway UTC cron settings); change the time through the Railway Cron service settings.
- Do not enable unattended weekly Google sync until OAuth publishing status and refresh-token behavior are verified. Google documents seven-day refresh-token expiration for external OAuth apps left in Testing status.

## Review Focus

- **Revoked or expired Google refresh token:** show reconnect-required, retain the last good report with its timestamp, and do not show stale metrics as current. Test in Tasks 2 and 8.
- **Partial API results or source quota/timeout:** mark the affected report incomplete and preserve the prior successful snapshot. Test in Tasks 3 and 8.
- **Unmapped GA4 invite event:** show setup-needed rather than reporting a zero conversion rate. Test in Tasks 4 and 6.
- **Low traffic or small conversion counts:** mark the finding inconclusive and avoid causal language. Test in Task 6.
- **Crawler redirect to a different host, private address, or disallowed path:** block the request and record the reason. Test in Task 5.

---

## File Structure

```text
backend/
  app/
    api/                 # HTTP routes and request/response schemas
    core/                # settings, login, crypto, database, logging
    connectors/          # Google APIs and public-site crawler
    services/            # sync, metric rules, report generation
    jobs/                # short-lived scheduled report command
    skills/              # SEO and Sparestracker marketing playbooks
  alembic/               # PostgreSQL schema migrations
  tests/                 # unit, API, and connector tests
frontend/
  src/                   # React app, route pages, API client, typed models
  tests/                 # component and browser tests
docs/setup/              # Google OAuth, local development, and deployment steps
```

## Task 1: Bootstrap the app and test harness

**Files:**
- Create: `backend/pyproject.toml`, `backend/app/main.py`, `backend/app/core/config.py`, `backend/tests/test_health.py`
- Create: `frontend/package.json`, `frontend/src/main.tsx`, `frontend/src/App.tsx`, `frontend/vite.config.ts`, `frontend/vitest.config.ts`, `frontend/tsconfig.json`
- Create: root `.gitignore`, `README.md`

**Interfaces:**
- Produces `GET /api/health -> {"status": "ok"}` and a typed frontend API client using same-origin `/api` routes.

- [ ] Write `test_health_returns_ok` and `test_health_route_has_no_auth_dependency`.
- [ ] Run `cd backend && pytest tests/test_health.py -q`; confirm the route is missing.
- [ ] Implement the FastAPI app and health route; configure the Vite client, Vitest, and React Testing Library to serve and test the basic private-app shell.
- [ ] Run `cd backend && pytest -q` and `cd frontend && npm test -- --run`; both must pass.
- [ ] Commit as `chore: bootstrap marketing agent app`.

## Task 2: Add owner login, Google OAuth, and encrypted credentials

**Files:**
- Create: `backend/app/core/auth.py`, `backend/app/core/crypto.py`, `backend/app/api/auth.py`, `backend/app/models/connection.py`, `backend/app/db.py`, `backend/alembic/versions/001_connections.py`
- Create: `backend/tests/test_auth.py`, `backend/tests/test_crypto.py`, `docs/setup/google-oauth.md`, `backend/.env.example`
- Modify: `backend/app/main.py`, `backend/app/core/config.py`

**Interfaces:**
- `GET /api/auth/google/start -> {"authorization_url": str}`
- `GET /api/auth/google/callback?code=...&state=... -> 303` to the app after validating the owner and OAuth state.
- `GET /api/auth/me -> {"email": str}`; `POST /api/auth/logout -> 204`.
- `DELETE /api/connections/google -> 204` revokes the saved connection and deletes its stored OAuth credentials.
- `encrypt_secret(plaintext: str) -> str` and `decrypt_secret(ciphertext: str) -> str`.
- Persist one connection record containing encrypted OAuth credentials; store no client secret in source control.

- [ ] Write tests `test_non_owner_cannot_start_session`, `test_oauth_state_mismatch_is_rejected`, `test_oauth_nonce_and_issuer_are_validated`, `test_session_required_for_private_routes`, `test_token_round_trips_through_encryption`, `test_token_is_not_returned_by_connection_api`, and `test_expired_refresh_token_requires_reconnect`.
- [ ] Run `cd backend && pytest tests/test_auth.py tests/test_crypto.py -q`; confirm expected failures.
- [ ] Implement owner allowlisting, signed HttpOnly/Secure/SameSite session cookies, OAuth state/nonce/issuer/audience validation, offline refresh-token handling, and authenticated encryption using an environment-managed key.
- [ ] Add setup documentation for Google Cloud APIs, `openid`, `email`, `profile`, `analytics.readonly`, `webmasters.readonly`, the owner test account, callback URL, and the OAuth production-status check.
- [ ] Run the auth and crypto test files; all tests must pass, including the refresh-token reconnect case.
- [ ] Commit as `feat: add private Google authentication`.

## Task 3: Connect Google properties and build report clients

**Files:**
- Create: `backend/app/connectors/google_auth.py`, `backend/app/connectors/search_console.py`, `backend/app/connectors/ga4.py`, `backend/app/api/connections.py`
- Create: `backend/app/schemas/google.py`, `backend/tests/connectors/test_google_properties.py`, `backend/tests/connectors/test_search_console.py`, `backend/tests/connectors/test_ga4.py`
- Modify: `backend/app/main.py`, `backend/app/core/config.py`

**Interfaces:**
- `GET /api/connections/google/properties -> {"search_console": list[SearchConsoleProperty], "ga4": list[GA4Property]}`.
- `PUT /api/connections/google/selection` accepts one Search Console site URL and one GA4 property ID.
- `DELETE /api/connections/google -> 204` disconnects Google, clears selected properties, and removes stored Google report data.
- `query_search_performance(site_url: str, start_date: date, end_date: date) -> ConnectorResult[list[SearchRow]]`.
- `query_ga4(property_id: str, start_date: date, end_date: date, event_names: list[str]) -> ConnectorResult[list[GA4Row]]`.
- `SearchRow` carries `date`, `query`, `page`, `clicks`, `impressions`, `ctr`, and `position`.
- `GA4Row` carries requested dimensions (landing page, session source/medium, event name) plus `sessions`, `engagement_rate`, and `event_count`.
- `ConnectorResult[T]` carries `data`, `retrieved_at`, `complete`, and optional `warning`.

- [ ] Write connector tests for property selection, no accessible properties, successful rows, partial/empty rows, revoked authorization, quota response, and timeout.
- [ ] Run `cd backend && pytest tests/connectors -q`; confirm the connector modules are missing.
- [ ] Implement official Search Console, GA4 Data, and GA4 Admin clients with bounded date ranges, explicit read-only scopes, normalized rows, and typed partial/error results. Document which Google Cloud APIs must be enabled.
- [ ] Add property selection persistence and authenticated routes; never return OAuth credential fields.
- [ ] Run connector tests; all mocked success and failure cases must pass.
- [ ] Commit as `feat: add Google reporting connectors`.

## Task 4: Normalize metrics and map the invite funnel

**Files:**
- Create: `backend/app/schemas/metrics.py`, `backend/app/services/event_mapping.py`, `backend/app/services/metric_comparison.py`, `backend/app/api/settings.py`
- Create: `backend/tests/services/test_event_mapping.py`, `backend/tests/services/test_metric_comparison.py`
- Modify: `backend/app/models/connection.py`, `backend/alembic/versions/002_reporting_settings.py`

**Interfaces:**
- `save_event_mapping(cta_event: str | None, invite_submit_event: str | None) -> ReportingSettings`.
- `compare_periods(current: list[MetricPoint], previous: list[MetricPoint]) -> list[MetricDelta]`.
- `GET /api/settings/reporting` and `PUT /api/settings/reporting` read and update property selection and event mapping.
- `MetricPoint` fields are `date`, `metric`, and `value`; `MetricDelta` fields are `metric`, `current_value`, `previous_value`, `absolute_change`, nullable `percent_change`, and `status` (`comparable` or `no_baseline`).
- `ReportingSettings` fields are `site_url`, `search_console_site`, `ga4_property_id`, `cta_event`, and `invite_submit_event`.
- Persist selected source property IDs and event names; never persist form submissions or contacts.

- [ ] Write `test_unmapped_invite_event_is_setup_needed`, `test_event_mapping_uses_configured_names`, `test_period_comparison_uses_equal_length_windows`, and `test_zero_baseline_has_defined_delta_state`.
- [ ] Run the two service test files and confirm failures before implementation.
- [ ] Implement configurable event mappings and period comparison for clicks, impressions, CTR, average position, landing-page activity, CTA counts, and invite submissions.
- [ ] Run the service tests; all edge cases must pass without emitting a false conversion rate for an unmapped event.
- [ ] Commit as `feat: add invite funnel metrics`.

## Task 5: Build the bounded technical SEO crawler

**Files:**
- Create: `backend/app/connectors/site_crawler.py`, `backend/app/schemas/audit.py`, `backend/tests/connectors/test_site_crawler.py`
- Modify: `backend/app/core/config.py`

**Interfaces:**
- `crawl_site(site_url: str, max_pages: int = 100) -> CrawlResult`.
- Each `PageAudit` records URL, HTTP status, title, description, canonical, robots/indexability, H1 count, link counts, and issue codes.

- [ ] Write tests for sitemap discovery, page limit, robots disallow, title/description/canonical/H1 checks, broken links, external redirect rejection, localhost/private-IP rejection, and timeout/oversized response handling.
- [ ] Run `cd backend && pytest tests/connectors/test_site_crawler.py -q`; confirm failures.
- [ ] Implement same-domain crawling with robots compliance, configurable page/request/time/response limits, DNS-pinned public-IP validation, safe redirects, and clear audit issues.
- [ ] Run the crawler test file; every unsafe or disallowed URL must be blocked before fetching.
- [ ] Commit as `feat: add safe technical SEO crawler`.

## Task 6: Generate evidence-linked recommendations

**Files:**
- Create: `backend/app/skills/seo.md`, `backend/app/skills/sparestracker-marketing.md`, `backend/app/schemas/recommendation.py`, `backend/app/services/analysis.py`, `backend/app/services/recommendation_generator.py`
- Create: `backend/tests/services/test_analysis.py`, `backend/tests/services/test_recommendation_generator.py`
- Modify: `backend/app/core/config.py`

**Interfaces:**
- `analyze_report(search_rows: list[SearchRow], ga_rows: list[GA4Row], crawl: CrawlResult, settings: ReportingSettings) -> list[Finding]`.
- `Finding` fields are `code`, `title`, `summary`, `source`, `evidence`, and `limitations`.
- `Recommendation` fields: `finding`, `evidence`, `suggested_action`, `measurement`, `confidence`, `limitations`.
- `generate_recommendations(findings: list[Finding]) -> list[Recommendation]`.
- Use one OpenAI model configured by `OPENAI_MODEL`; no model selector or fallback. Supply only the findings and aggregates needed for the current answer.

- [x] Write tests for the CTR opportunity, low sample, missing event mapping, evidence-linked recommendations, and invalid model evidence.
- [x] Run the focused test files and confirm failures before implementation.
- [x] Implement deterministic thresholds and focused playbooks; generate structured recommendations and validate every cited metric against supplied findings.
- [x] Run service and backend tests with a mocked language-model client; unsupported-cause, missing-data, and low-volume cases are handled.
- [ ] Commit as `feat: generate evidence-based SEO recommendations`.

## Task 7: Add report history, chat, and weekly summaries

**Files:**
- Create: `backend/app/models/report.py`, `backend/app/services/report_runner.py`, `backend/app/jobs/weekly_report.py`, `backend/app/api/reports.py`, `backend/app/api/chat.py`
- Create: `backend/alembic/versions/003_reports.py`, `backend/tests/services/test_report_runner.py`, `backend/tests/jobs/test_weekly_report.py`, `backend/tests/api/test_reports.py`
- Modify: `backend/app/main.py`, `backend/app/db.py`

**Interfaces:**
- `POST /api/reports/run -> ReportSummary`.
- `POST /api/reports/run` accepts ISO `start_date` and `end_date`; when omitted, analyze the latest 28 complete days and compare with the preceding 28 days.
- `GET /api/reports?limit=20 -> list[ReportSummary]`; `GET /api/reports/{report_id} -> ReportDetail`.
- `DELETE /api/reports/{report_id} -> 204` deletes the selected saved report.
- `POST /api/chat` accepts `{question: str, report_id: str | None}`; when report ID is omitted, use the latest saved report. Return an answer with source/evidence references.
- `ReportSummary` fields are `id`, `created_at`, `date_range`, `status`, `finding_count`, and `source_timestamps`; `ReportDetail` adds metrics, crawl issues, and recommendations.
- `python -m app.jobs.weekly_report` runs one report, persists the result, closes database resources, and exits with a status code.
- Railway Cron runs the command Monday 08:00 Africa/Nairobi (`0 5 * * 1` UTC); it writes to the dashboard and never sends email.
- Persist only aggregate evidence and findings; do not store raw API payloads. Keep saved reports until the owner deletes them or disconnects Google.
- Weekly runs analyze the most recently completed EAT Monday-to-Sunday week against the prior week; label source data that has not finished processing.

- [x] Write tests for report persistence, equal date windows, failed sync preserving last good report, reconnect-required state, duplicate weekly-job invocation for the same week, proper database cleanup/exit, report deletion, Google disconnect data cleanup, and chat answers limited to retrieved evidence.
- [x] Run the service, job, and API tests; all pass.
- [x] Implement saved report runs, report retrieval, evidence-grounded chat, and an idempotent one-shot weekly report command.
- [x] Run the full backend suite and SQLite migration; compile the migration chain against PostgreSQL's dialect. A live PostgreSQL integration server is not available in this workspace.
- [ ] Commit as `feat: add saved and scheduled reports`.

## Task 8: Build the private web interface

**Files:**
- Create: `frontend/src/api/client.ts`, `frontend/src/api/types.ts`, `frontend/src/pages/SetupPage.tsx`, `frontend/src/pages/ReportPage.tsx`, `frontend/src/pages/ChatPanel.tsx`, `frontend/src/pages/ConnectionsPage.tsx`
- Create: `frontend/src/components/MetricEvidence.tsx`, `frontend/src/components/ConnectionStatus.tsx`, `frontend/tests/`
- Modify: `frontend/src/App.tsx`, `frontend/src/main.tsx`

**Interfaces:**
- Setup flow connects Google, selects properties, sets site domain, and maps CTA/invite events.
- Report view selects dates, shows comparison, technical audit findings, recommendation evidence, source timestamps, and saved reports.
- Chat view submits questions and displays answers with evidence references.

- [x] Write component tests for the owner sign-in gate, Google connection states, missing event mapping, stale report warning, partial-data warning, evidence rendering, and report deletion/disconnect controls.
- [x] Run `cd frontend && npm test -- --run`; all 6 tests pass.
- [x] Implement responsive setup, report, and chat views using typed API calls and explicit loading, empty, and error states.
- [ ] Add and run Playwright smoke tests. Playwright and a browser binary are not available in this workspace; the frontend component suite and production build pass.
- [ ] Run frontend unit and browser tests; the browser test remains outstanding.
- [ ] Commit as `feat: add private marketing dashboard`.

## Task 9: Deploy privately and verify source-to-report accuracy

**Files:**
- Create: `Dockerfile`, `docs/setup/deployment.md`, `docs/setup/report-validation.md`
- Modify: `README.md`, `backend/.env.example`

**Interfaces:**
- Web and cron services use environment variables for database URL, owner email, session signing key, token encryption key, Google OAuth client ID/secret, OAuth redirect URI, OpenAI API key/model, and public base URL.
- Build the Vite frontend into the FastAPI static directory so web UI and API use one origin; expose only the authenticated app and health route.
- Configure the cron service to run the one-shot job and exit, using the same image and environment secrets as the web service.

- [x] Add deployment checks for missing secrets, production secure-cookie settings, database migration, and the UTC cron expression for the Africa/Nairobi schedule.
- [x] Run the complete backend and frontend suites locally; build the Python distributions and compile the full migration chain for PostgreSQL. A live PostgreSQL integration server and Docker builder are not available in this workspace.
- [ ] Deploy the private web app and PostgreSQL, add a Railway Cron service using `0 5 * * 1` with start command `python -m app.jobs.weekly_report`, and configure the OAuth callback, owner account, and API credentials without committing secrets. Deployment is blocked on a remote source repository and the owner's Google/OpenAI secret values.
- [ ] Compare a sample Search Console and GA4 report against portal UI values; document expected timing, data gaps, and any API limitations.
- [ ] Verify login rejection for any non-owner account, disconnect/delete behavior, weekly report timestamp in Africa/Nairobi, correct cron execution, and stale-token alerting.
- [x] Commit the local deployment package and validation docs as `docs: document private deployment and report validation`.

## Execution Notes

- Create the **private** GitHub repository `sparestracker-marketing-agent` during implementation setup, then push the existing design/spec commit and this plan before the first code task.
- Keep all Google and OpenAI credentials in deployment secrets or local ignored environment files.
- During Google OAuth development, add the owner as a test user. Before enabling unattended weekly sync, verify the OAuth app's publishing status and any required scope verification; testing-mode refresh tokens may expire after seven days.
- Store App Store Connect and Google Play tasks in a separate follow-up plan after the mobile apps are published and the available growth reports are confirmed.

## Official References

- [Google Search Console API authorization](https://developers.google.com/webmaster-tools/v1/how-tos/authorizing)
- [Google Search Console Search Analytics query](https://developers.google.com/webmaster-tools/v1/searchanalytics/query)
- [Google Analytics Data API overview](https://developers.google.com/analytics/devguides/reporting/data/v1)
- [Google OAuth 2.0 for web server applications](https://developers.google.com/identity/protocols/oauth2/web-server)
- [Google OAuth status and refresh-token lifetime](https://developers.google.com/identity/protocols/oauth2)
- [Railway Cron Jobs](https://docs.railway.com/cron-jobs)
