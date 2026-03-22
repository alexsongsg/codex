# 2026 CEO Dashboard

## HubSpot Setup Runbook v2

Date: 2026-03-22  
Scope: `CEO Dashboard HubSpot Sync` setup and operations

## 1. Outputs

HubSpot sync writes:

- `reports/ceo_dashboard/hubspot_source_latest.json`
- `reports/ceo_dashboard/hubspot_metrics_history.csv`

## 2. Required Secret

- `HUBSPOT_PRIVATE_APP_TOKEN` (required)

Optional:

- `HUBSPOT_QUALIFIED_STAGE_IDS`
- `HUBSPOT_REGION_TARGETS_JSON`
- `CEO_DASHBOARD_CURRENCY` (default `USD`)

## 3. Preflight (Mandatory Before Run)

Run:

```powershell
powershell -ExecutionPolicy Bypass -File E:\CodeX\scripts\selfcheck_codex_env.ps1 -RequireHubspotToken
```

Pass criteria:

- `python` available
- `gh` available
- `HUBSPOT_PRIVATE_APP_TOKEN` available

## 4. Dry Run

```powershell
python E:\CodeX\scripts\sync_ceo_dashboard_from_hubspot.py --dry-run
```

Validation checkpoints:

- `metrics.company_totals.won_revenue_ytd` should not be zero (unless business truth is zero)
- `metrics.company_totals.next_90d_forecast` should not be zero (unless business truth is zero)
- `metrics.region_breakdown[*].region` should be limited to CEO region codes:
  `GKA, CHN, SGP, MYS, PHL, THI, IDO, LAT`

## 5. Production Run

```powershell
python E:\CodeX\scripts\sync_ceo_dashboard_from_hubspot.py ^
  --output-json E:\CodeX\reports\ceo_dashboard\hubspot_source_latest.json ^
  --history-csv E:\CodeX\reports\ceo_dashboard\hubspot_metrics_history.csv
```

## 6. Baseline Verification (2026-03-22)

Production run completed on 2026-03-22 with:

- `won_revenue_ytd = 1549224028.8`
- `next_90d_forecast = 8598347.0`
- region set = `CHN,GKA,IDO,LAT,MYS,PHL,SGP,THI`
- non-CEO region codes = none

## 7. Notes

- Full HubSpot sync can take several minutes due to paged, sequential API reads across deals/companies/owners/pipelines.
