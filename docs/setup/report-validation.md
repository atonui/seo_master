# Report validation checklist

Before using recommendations for decisions, compare a completed sample report with the source portals.

1. Select one Search Console property and a date range whose data has finished processing. Compare the daily clicks, impressions, average position, and CTR values with Search Console. The report uses date aggregates for totals and query/page rows only for drill-down opportunities.
2. Select one GA4 property. Compare sessions and engagement rate with the same GA4 date range. Confirm the GA4 reporting identity and timezone used by the property.
3. Map the CTA and invitation submission event names to the exact GA4 event names. Compare event counts before interpreting the funnel. The app does not report conversions when the invitation event is unmapped.
4. Check the website crawl issues against the page source and robots directives. The crawler is bounded and cannot reliably inspect content rendered only by JavaScript.
5. Inspect each recommendation’s source, period, observed value, and limitations. The recommendation generator may select actions but cannot supply new evidence IDs.

Search Console and GA4 may process data with a delay. Default manual reports use a three-day lag. Weekly reports cover the last completed Monday–Sunday in Nairobi time. An incomplete source marks the report partial; a sync that fails before receiving usable source data leaves saved reports untouched. Deleting a report removes that report. Disconnecting Google deletes saved reports and locally stored Google credentials.

Record the validation date, selected property names, checked date ranges, source portal values, and any known mismatches here before enabling unattended report runs.
