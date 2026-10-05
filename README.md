# Visa & Regulatory Change Monitor

Module 4 of the overseas health market intelligence brief: track visa, migration, education and
regulatory changes that may shift demand for OSHC, OVHC and OWHC.

```
sources -> collectors -> classify -> JSON Lines store -> S3 -> Athena views -> Tableau / Power BI
                                  \-> alerts (file, SNS, webhook)      \-> Streamlit prototype
```

## What maps to the brief

| Brief | Where |
|---|---|
| Phase 1: web scraping framework | `collectors.py` (HTML listing, RSS/Atom, page-change detection; robots.txt, delay, user agent) |
| Phase 1: source inventory | `sources.py` -> `source_inventory.csv` |
| Phase 1: data storage structure | `storage.py` (JSON Lines in `dt=` partitions), `aws_s3.py`, `athena_setup.py` |
| Phase 2: categorisation, visa tagging | `classify.py` (visa category, products affected, change type, effective date, impact) |
| Phase 3: dashboard | `dashboard_app.py` prototype; Tableau/Power BI build notes below |
| Phase 3: automated refresh, alerting | `run_pipeline.py --aws` on a schedule; `alerts.py` (High -> SNS / Teams / Slack) |
| Phase 4: weekly report | `weekly_report.py` (facts generated, opportunities left to the analyst) |
| Dashboard output: summary, effective date, impact, visa categories, source link | the change feed, and the `v_visa_changes` view |
| Alert categories High / Medium / Low | `impact` field; High alerts push out, Medium are logged for the digest |
| Success criterion 5 (which changes could affect future demand) | feed + "coming into effect" + trend charts |

Competitor pricing, promotions and partnerships (criteria 1-4, 6) are other modules. `alerts.py` uses a
generic `alert_type` so they can write to the same alert stream.

## Run it

```bash
pip install -r requirements.txt
python -m pytest -q                      # parsers and classifier
python run_pipeline.py --offline         # synthetic demo data, no network
streamlit run dashboard_app.py           # opens on the demo data until live data exists
python weekly_report.py --sample         # demo report in reports/
python run_pipeline.py                   # live: collect, classify, store, alert
```

## Getting real data

Each source was opened on 3 Oct 2026 to see what it really serves. This is what was found:

| Source | Result |
|---|---|
| Study Australia news | Works. Dated items (visa charge, CRICOS provider pause, 2027 settings). Article URLs look like `.../news/<slug>`. |
| Migration Institute of Australia media releases | Works. Dated list, but every release is a **PDF**, so only the title and listing date are used. |
| Fair Work Ombudsman media releases | Titles and dates load. The link pattern is assumed. Most releases are unrelated and are dropped. |
| Department of Education ministers | Real releases exist at `ministers.education.gov.au/<minister>/<slug>`. The listing page is not confirmed. |
| Home Affairs news archive | The page loaded as an empty template, so its list may be built by JavaScript. |
| Home Affairs student-visa and processing-times pages | Followed by change detection (a changed page becomes a record). |
| Removed | Google News RSS (its robots.txt disallows it), the Home Affairs ministers landing page (stale since 2022), VisaConnect (promotional, anchor links), and URLs that returned 404. |

**The collectors have not run against the live sites.** The sandbox this was built in could only view the pages through
a limited reader, so the parsers are tested on HTML modelled on what that reader showed. On your own computer, run:

```bash
python diagnose_source.py study_australia     # status, links found, sample items, feeds, suggested link_pattern
python diagnose_source.py mia
python run_pipeline.py --only study_australia mia --no-notify
```

`diagnose_source.py` prints the HTTP and robots.txt result, how many links the page has, which ones your `link_pattern`
keeps, the most common URL folders (use one as the pattern), any RSS/Atom feed the page advertises (used automatically),
and a warning when the page looks JavaScript-rendered. Fix `link_pattern` in `sources.py` until the sample items look right,
then run everything.

Things to expect with real data:

- Items without a date next to the link are dated by the day they were first seen (the rationale says so).
- PDF-only and title-only items carry less text, so they score lower than items with full article text.
- An item with no recognisable visa or regulatory wording is dropped. Check the "classified X of Y" line to see how many.
- Etiquette is built in: robots.txt is checked (a site that cannot be checked is skipped), requests are spaced out, and
  `USER_AGENT` identifies you. Put your email in it.

## Adding items by hand

For anything that cannot be scraped (a LinkedIn post, a PDF notice), create `data/manual_items.json` and run the
pipeline as normal. It also gives you real data to test the AWS steps with before the scrapers are tuned.

```json
[
  {
    "title": "Title of the announcement",
    "url": "https://link-to-the-original-source",
    "published": "2026-10-01",
    "body": "Paste the key paragraph here so the classifier can read it.",
    "source_id": "linkedin"
  }
]
```

`title` and `url` are required. `source_id` must be one of the ids in `sources.py` (default `linkedin`).

## How a change is classified

Each record carries its reasoning in `impact_rationale`, so scores can be explained and challenged.

- **Relevance filter**: items with no visa, migration, student or sponsor language are dropped (most Fair Work releases).
- **Visa categories**: regex tags for subclasses 500, 590, 485, 482, 407, 408, 417/462, 600, skilled and employer PR,
  partner/family, and a general "all temporary visas".
- **Products affected**: student -> OSHC; 482/407 -> OWHC; 485/408/working holiday -> OVHC + OWHC; visitor -> OVHC;
  permanent pathways -> none. **This mapping is an assumption. Confirm it with the product team.**
- **Change type**: cap/quota, closure/pause, eligibility, fee, compliance, new pathway, processing, workplace compliance.
- **Effective date**: phrases like "from 1 July 2026", "takes effect today"; a year-less date rolls into next year when needed.
- **Impact score**: change-type weight (capped at 6) + 2 for student visas or 1 for other product-linked visas + 1 for
  three or more categories + 1 if effective within 90 days. High >= 6, Medium 4-5, Low < 4. Tune the weights in `classify.py`.

The rules are keyword-based, so expect false positives and misses. Review High items before they are circulated.

## Data model

One JSON object per line, in `data/live/dt=YYYY-MM-DD/changes_HHMMSS.jsonl` (`dt` = day first seen):
`id, source_id, source_name, org_type, title, summary, url, published_date, effective_date, change_types[],
visa_categories[], products_affected[], impact, impact_score, impact_rationale, is_sample, first_seen`.
`id` is a hash of the URL, so re-runs never create duplicates. Demo data is stored separately in `data/sample/`
and `--aws` refuses to upload it.

## AWS setup

1. IAM: create a user with a policy based on `iam_policy.json` (replace the bucket and topic names). Create an access key.
2. Copy `.env.example` to `.env` and fill in the keys, a globally unique bucket name and the region.
3. `python run_pipeline.py --aws` creates a private bucket, uploads new files, then creates the Athena database, table
   (JSON SerDe with partition projection on `dt`) and two views.
4. Optional alerts: create an SNS topic, subscribe your email, put the ARN in `SNS_TOPIC_ARN`. A Teams or Slack
   incoming webhook URL in `ALERT_WEBHOOK_URL` works too.

The S3, Athena and SNS code was not run against a real AWS account. If a statement fails, the error text from Athena will
name the column or property.

## Connect Tableau

Use Tableau Desktop (Tableau Public has no Athena connector). Install the Amazon Athena JDBC driver from Tableau's driver
page into `C:\Program Files\Tableau\Drivers` (Windows) or `~/Library/Tableau/Drivers` (Mac), restart, then
**Connect -> To a Server -> Amazon Athena**: server `athena.ap-southeast-2.amazonaws.com`, port 443, S3 staging directory
= `ATHENA_OUTPUT`, plus the access key pair. Pick database `dashboard_db` and drag `v_visa_changes` onto the canvas
(add `v_visa_changes_by_category` as a second source for visa-type frequency). Use an Extract to avoid per-click query cost.

Sheets to build:

1. **Change feed**: text table of published date, effective date, impact, title, summary, visa categories, link
   (set the URL field as an action: Dashboard -> Actions -> Go to URL).
2. **Frequency by month**: `MONTH(published_date)` x `COUNT(id)`, stacked by `impact`; use one blue ramp, High darkest.
3. **Visa categories**: bar of `COUNTD(id)` by `visa_category` from the by-category view, sorted descending, one colour.
4. **Coming into effect**: filter `effective_date` between today and today + 90 days, sorted ascending.
5. Dashboard filters: published date, impact, visa category, products affected, source. Apply to all sheets.

No-AWS fallback: `run_pipeline.py` also writes `data/<store>/export/changes_flat.csv` and
`changes_by_visa_category.csv`, which Tableau and Power BI both open directly.

## Power BI (preferred in the brief)

Same data, two routes: import the two CSVs above, or use the Athena ODBC driver with a DSN pointing at the views.
Build the same five visuals; scheduled refresh needs a gateway for ODBC. Check with your supervisor which tool is
expected, since the brief prefers Power BI.

## Automated refresh

`python run_pipeline.py --aws` is idempotent, so schedule it daily. Options: cron on a server; a container scheduler
using the included `Dockerfile` (for example EventBridge -> ECS Fargate); or a GitHub Actions cron job with the AWS keys
as repository secrets. Then schedule the Tableau or Power BI extract refresh a little after it.

## Cost and housekeeping

Athena charges per data scanned and these files are tiny. Delete the bucket, database and access key when the
assignment is finished.

## Google Sheets for Tableau

`python run_pipeline.py --sheets` rewrites two tabs (`changes`, `by_category`) in a Google Sheet from the local
live store, so Tableau can read them with a normal Google sign-in (no AWS keys). Combine flags as needed, for
example `python run_pipeline.py --aws --sheets --no-notify`.

One-time setup:
1. Google Cloud console: create a project, enable **Google Sheets API** and **Google Drive API**.
2. IAM & Admin > Service accounts > create one > Keys > Add key > JSON. Save it as `google-key.json` in the project folder (it is gitignored).
3. Open your Google Sheet > Share > add the service account's e-mail (`...@...iam.gserviceaccount.com`) as **Editor**.
4. In `.env` set `GOOGLE_SHEET_ID` (the long id in the sheet's address) and `GOOGLE_SERVICE_ACCOUNT_FILE=google-key.json`.
5. `pip install -r requirements.txt`, then `python run_pipeline.py --sheets`.

The tabs are rewritten each run, so repeats never create duplicates. The data comes from this machine's `data/live`
folder; run the pipeline from the same machine each day so history accumulates.
