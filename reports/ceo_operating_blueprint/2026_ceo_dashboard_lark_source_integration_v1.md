# 2026 CEO Dashboard

## Lark Sheet Data Source Integration v1 (P0)

Date: 2026-03-22  
Status: Ready for implementation

## 1. Goal

Use the designated Lark Sheet as CEO Dashboard source-of-truth for `Revenue Actual YTD`, with automatic refresh and audit trail.

This aligns with locked decision `D-001` in the metric decision log.

## 2. Scope

### P0 (this delivery)

- auto-sync `Revenue Actual YTD`
- write normalized dashboard source JSON
- append historical snapshot log for traceability
- support manual and scheduled trigger in GitHub Actions

### Out of scope (P1+)

- all engine-level metrics
- region-level metrics
- writeback to Lark
- finance reconciliation automation

## 3. Data Contract (P0)

Output file: `reports/ceo_dashboard/source_latest.json`

```json
{
  "dashboard": "CEO Dashboard",
  "version": "v1",
  "generated_at_utc": "2026-03-22T01:15:00+00:00",
  "metrics": [
    {
      "metric_name": "Revenue Actual YTD",
      "value": 1234567.89,
      "as_of_date": "2026-03-22",
      "currency": "USD",
      "source_type": "lark_sheet",
      "source_ref": "spreadsheet_token/sheet_id!B2",
      "synced_at_utc": "2026-03-22T01:15:00+00:00"
    }
  ]
}
```

History file: `reports/ceo_dashboard/revenue_actual_ytd_history.csv`

## 4. Integration Pattern

Script: `scripts/sync_ceo_dashboard_from_lark.py`

Supported modes:

- `recognized_finals` (recommended for P0): from one row (default `Team=All Countries`), sum monthly `Mon Final` columns up to current month
- `cell`: read direct metric cell, e.g. `B2`
- `aggregate`: read table range and compute YTD sum from `Date` + `Revenue` columns

Recommendation:

- Start with `recognized_finals` mode to match management-recognized logic exactly.
- Keep `aggregate` mode as fallback if finance later standardizes row-level raw ledger export.

Business example:

- in March run: YTD = `Jan Final + Feb Final` (because `Mar Final` is not available yet)
- in April run: YTD = `Jan Final + Feb Final + Mar Final`

## 5. Required Secrets

Add these repository secrets before first run:

- `LARK_APP_ID`
- `LARK_APP_SECRET`
- `LARK_SPREADSHEET_TOKEN`
- `LARK_SHEET_ID`

Optional:

- `LARK_REVENUE_CELL` (default `B2`)
- `LARK_REVENUE_TABLE_RANGE` (default `A1:Z5000`)
- `LARK_REVENUE_DATE_COLUMN` (default `Date`)
- `LARK_REVENUE_AMOUNT_COLUMN` (default `Revenue`)
- `CEO_DASHBOARD_CURRENCY` (default `USD`)

## 6. Automation

Workflow: `.github/workflows/ceo-dashboard-lark-sync.yml`

Trigger:

- manual (`workflow_dispatch`)
- scheduled on weekdays (`01:15 UTC`)

Outputs:

- `reports/ceo_dashboard/source_latest.json`
- `reports/ceo_dashboard/revenue_actual_ytd_history.csv`
- artifact `ceo-dashboard-lark-sync`

## 7. Reliability Controls

- fail fast if required credentials are missing
- fail on Lark API non-zero error code
- keep immutable history rows for every sync
- keep one normalized latest JSON for dashboard ingestion

## 8. Go-Live Checklist

1. Confirm Lark app has read scope for target Sheet.
2. Configure all required secrets in GitHub repo.
3. Run manual workflow in `dry_run=true`, verify numeric output.
4. Run manual workflow in `dry_run=false`, verify JSON + history files.
5. Point CEO Dashboard reader to `reports/ceo_dashboard/source_latest.json`.
6. Observe two weekly cycles before adding more metrics.

## 9. Next Step (P1)

- add `Scenario Base / Commit / Stretch` from controlled config source
- add `Gap to Base / Commit / Stretch` derived layer
- add region mapping guardrail check (`SGM` rejection) in same pipeline

## 10. How To Connect Lark (Step-by-step)

### Step 1: Prepare the target Lark Sheet

- Pick one stable sheet as MVP source for `Revenue Actual YTD`.
- Recommended P0 layout (cell mode):
  - a fixed cell (for example `B2`) contains the latest YTD number.
- Optional P1 layout (aggregate mode):
  - one `Date` column and one `Revenue` column in a table range.

### Step 2: Create a Lark app for API access

- In Lark/Feishu developer console, create an internal app for this workspace.
- Enable Sheets read capability for the app.
- Publish/enable app so it can access the target spreadsheet.
- Record:
  - `App ID` -> used as `LARK_APP_ID`
  - `App Secret` -> used as `LARK_APP_SECRET`

### Step 3: Get spreadsheet identifiers

- Open the target sheet URL and extract:
  - Spreadsheet token -> `LARK_SPREADSHEET_TOKEN`
  - Sheet ID (tab id) -> `LARK_SHEET_ID`
- If using cell mode, decide the metric cell:
  - e.g. `B2` -> `LARK_REVENUE_CELL=B2`

### Step 4: Configure GitHub Actions secrets

In repository `Settings -> Secrets and variables -> Actions`, add:

- required:
  - `LARK_APP_ID`
  - `LARK_APP_SECRET`
  - `LARK_SPREADSHEET_TOKEN`
  - `LARK_SHEET_ID`
- optional:
  - `LARK_REVENUE_CELL` (default `B2`)
  - `LARK_REVENUE_TABLE_RANGE` (default `A1:Z5000`)
  - `LARK_REVENUE_DATE_COLUMN` (default `Date`)
  - `LARK_REVENUE_AMOUNT_COLUMN` (default `Revenue`)
  - `CEO_DASHBOARD_CURRENCY` (default `USD`)

### Step 5: First connection test

Run workflow `CEO Dashboard Lark Sync` manually:

1. `mode=cell`
2. `dry_run=true`
3. check artifact/output to confirm the metric value can be read

Then run:

1. `mode=recognized_finals`
2. `dry_run=false`
3. confirm files are generated:
   - `reports/ceo_dashboard/source_latest.json`
   - `reports/ceo_dashboard/revenue_actual_ytd_history.csv`

### Step 6: Enable automatic refresh

- Keep the scheduled trigger enabled (weekdays `01:15 UTC` in workflow).
- Dashboard should read from `reports/ceo_dashboard/source_latest.json`.

### Troubleshooting quick checks

- `Missing required secrets`:
  - one or more required secrets are not set in GitHub.
- `Lark API error`:
  - app permission not enabled or wrong spreadsheet/sheet token.
- empty metric:
  - check the configured `LARK_REVENUE_CELL` actually has numeric data.
