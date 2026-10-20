# Sparestracker Marketing Agent Design

**Status:** Design approved in conversation; awaiting review of this written specification  
**Date:** 2026-10-20

## 1. Purpose

Build a private marketing and SEO copilot for the owner of Sparestracker. It connects to the owner's reporting portals, analyzes website and acquisition performance, and recommends specific improvements with evidence. It is a private operator tool, separate from the Sparestracker customer product; it is not a multi-tenant SaaS feature.

The first release should help identify how appropriate service and engineering businesses find Sparestracker and whether they request an invitation or demo. Sparestracker is currently an invitation-only pilot, so qualified lead activity matters more than raw traffic.

## 2. Goals and success criteria

The first release is successful when the owner can:

1. Connect a Google account and select the Sparestracker properties in Search Console and Google Analytics 4.
2. Run a technical audit of the public marketing site.
3. Review search performance, traffic sources, and the invitation-request funnel over a selected period and compare it with a prior period.
4. Ask questions in chat and receive recommendations tied to source data.
5. Review saved reports and a weekly summary.
6. Disconnect a data source and remove retained report data.

Recommendations must show their supporting evidence, a concrete action, and a metric to measure after the change. The agent must say when evidence is insufficient.

## 3. Users and access

- One authorized user: the owner.
- Require application login; do not expose reports publicly.
- Google integrations request read-only scopes for the selected properties.
- Store OAuth refresh tokens encrypted at rest; do not include access tokens in prompts, reports, or application logs.
- Provide disconnect and data deletion controls for each connected source.

## 4. First-release scope

### 4.1 Google Search Console analysis

Read query and page performance for selected date ranges, including impressions, clicks, click-through rate, and average position. Identify query/page combinations with meaningful impressions and relatively weak click-through, pages losing visibility, and search terms that appear relevant to Sparestracker's target audience. Respect source API limits and report when data may be incomplete.

### 4.2 Google Analytics 4 analysis

Read aggregated traffic and landing page metrics, acquisition source/medium, and configured conversion events. Compare sessions and engagement with CTA activity and completed invitation requests. The app must allow event mapping to the site's actual event names rather than assuming a tracking schema.

Do not ingest names, email addresses, form contents, or other individual lead records. The agent needs aggregate counts and rates only.

### 4.3 Technical site audit

Crawl only the configured public Sparestracker domain. Check sitemap and robots directives, indexability, page titles and descriptions, canonical URLs, heading structure, internal links, and broken or redirected links. Report the affected URL and the observed issue. The crawler must respect robots directives and use bounded request rates and page limits.

### 4.4 Marketing analysis

Interpret findings for Sparestracker's product and audience: spare-parts inventory tracking for service departments and engineering businesses, with inventory activity connected to work orders. Prioritize qualified invitation/demo requests over vanity metrics. Suggest content or funnel experiments only when the evidence supports them.

### 4.5 Store reporting deferred

Add Apple App Store Connect and Google Play reporting after the iOS and Android apps are published. Use official reporting interfaces where they expose the needed data; support report exports where programmatic access does not cover acquisition or listing metrics. Store listing changes remain manual.

## 5. User experience

Provide a private web application with:

- A setup page to connect Google, choose Search Console and GA4 properties, set the site domain, and map conversion events.
- An audit/report view with date range, prior-period comparison, source timestamps, and links or labels identifying the data source.
- A chat interface for questions about the connected data and findings.
- Saved reports and a weekly summary.
- A clear connection status and last successful sync time for each source.

The agent must never publish content, edit website code, modify analytics configuration, change store listings, or send campaigns automatically.

## 6. Analysis and recommendation design

Use deterministic queries and calculations for reported values and comparisons. The language model may interpret these results, but may not invent or recalculate source values without showing its method.

Each recommendation contains:

- Finding: the observed change or issue.
- Evidence: source, date range, values, and comparison baseline.
- Suggested action: a specific fix or experiment.
- Measurement: the metric and period to use to assess the result.
- Confidence: high, medium, or low, with a brief reason.

Suppress causal claims when the data only shows correlation. For small samples, label the result as inconclusive and suggest gathering more data. When a source is disconnected, stale, incomplete, or returns an API error, surface that state and do not present the affected analysis as current.

## 7. Data flow and storage

1. The owner authorizes read-only access to a Google account and selects properties.
2. The backend retrieves bounded, aggregated reports and public-site crawl results.
3. The backend normalizes metrics, records the source and retrieval time, and stores the minimum data needed for period comparisons and report history.
4. Analysis rules calculate changes and candidate issues.
5. The language model receives only the relevant aggregates and audit findings and produces structured recommendations.
6. The UI renders recommendations alongside the evidence and allows follow-up questions.

Retain aggregated report data and crawl findings only while needed for saved comparisons. Do not retain personally identifiable lead data. Provide a way to delete stored reports and disconnect sources. Exact retention duration and deployment provider will be set in the implementation plan.

## 8. Application architecture

- Private browser-based UI for setup, reports, and chat.
- Python/FastAPI backend for authentication, OAuth callbacks, source connectors, scheduled sync, crawling, analysis, and report APIs.
- Separate connector modules for Search Console, GA4, and the website crawler so each can be tested independently.
- A small persistence layer for encrypted connection credentials, selected property configuration, aggregate snapshots, audit runs, and generated reports.
- A skill/playbook layer with focused SEO, marketing funnel, and later app-store analysis instructions. The playbooks guide interpretation; they do not grant portal access.
- No customer accounts, multi-tenant abstractions, or writes to external portals in the first release.

The frontend framework, storage engine, and deployment provider are implementation choices. The implementation plan should prefer the simplest secure setup that supports OAuth callbacks, saved reports, and scheduled weekly analysis.

## 9. Failure handling

- Show clear connection, permission, quota, timeout, and stale-data states.
- Retry transient source failures with bounded backoff; do not silently treat failed syncs as empty data.
- Preserve the last successful report and label its timestamp when a new sync fails.
- Treat missing event configuration and low traffic as setup/data limitations, not marketing conclusions.
- Keep a short operational log without tokens, personal lead details, or raw form contents.

## 10. Verification

- Unit-test metric normalization, period comparisons, event mapping, and recommendation thresholds with synthetic fixtures.
- Test connector behavior with mocked API responses, including empty results, incomplete results, expired authorization, quota errors, and timeouts.
- Compare a sample of fetched metrics against the corresponding portal reports before relying on generated recommendations.
- Test the crawler against known pages and links, including redirects, broken links, noindex pages, and robots restrictions.
- Review sample recommendations for traceability, unsupported causal claims, and low-volume handling.
- Confirm that logs and model inputs contain no OAuth secrets or individual lead data.

## 11. Rollout

1. Create the standalone private application and configure single-owner login.
2. Connect Search Console and GA4 and confirm the selected properties.
3. Inspect the Sparestracker marketing site and map its invitation-request events.
4. Implement the technical audit, period comparisons, and evidence-linked recommendations.
5. Validate reports against the source portals and enable the weekly summary.
6. Add store reporting after the apps are available in their respective stores.

## 12. Open implementation decisions

- Final frontend framework and visual components.
- Database choice and deployment provider.
- Google OAuth consent configuration and redirect domain.
- Actual site URL and whether GA4/Search Console properties are already configured for it.
- Actual invitation request event names and the weekly report delivery surface.

These decisions do not change the approved scope; resolve them during implementation planning or setup without expanding the product into a customer-facing service.
