# 2026 CEO Dashboard

## HubSpot Commercial Metric Spec v1

Date: 2026-03-22  
Status: Finalized baseline (v1)

## 1. Scope

This spec defines the commercial-layer metrics sourced from HubSpot for CEO Dashboard.

In scope:

- `won_revenue_ytd`
- `qualified_pipeline`
- `next_90d_forecast`
- `region_breakdown`

Out of scope:

- Finance recognized revenue (`Revenue Actual YTD` remains from Lark/Finance source chain)

## 2. Source Objects

Required HubSpot objects:

- Deals
- Companies
- Owners
- Deal Pipelines/Stages

## 3. Metric Definitions

### 3.1 `won_revenue_ytd`

Definition:

- Sum of `deal.amount` for deals recognized as won within YTD window.

YTD window:

- Start: `YYYY-01-01 00:00:00 UTC`
- End: `as_of_date 23:59:59 UTC`

Won determination order:

1. Stage is in pipeline metadata won set (`isWon=true`).
2. Property fallback (`hs_is_closed_won` / `is_closed_won` / `closed_won` in `{true,1,yes}`).
3. Stage id/label name fallback contains `won` and not `lost`.

Won timestamp:

- Primary: `closedate`
- Fallback: `hs_lastmodifieddate`

### 3.2 `qualified_pipeline`

Definition:

- Sum of `deal.amount` where deal stage belongs to `qualified_stage_ids`.

`qualified_stage_ids` source:

- Primary: `HUBSPOT_QUALIFIED_STAGE_IDS`
- Fallback: all non-closed stages inferred from pipeline metadata

### 3.3 `next_90d_forecast`

Definition:

- Sum of near-term forecast amount for qualified deals.

Rules:

1. If `closedate` exists and is within `[as_of_date, as_of_date+90d]`, add full `amount`.
2. If `closedate` is missing, fallback to forecast fields:
   - `forecast_category in {commit, bestcase, best_case}`
   - weight = `hs_forecast_probability` (normalized to 0-1) when provided
   - fallback weight = `1.0` for `commit`, `0.6` for `bestcase/best_case`
   - add `amount * weight`

## 4. Region Normalization

Allowed CEO region codes:

- `GKA`, `CHN`, `SGP`, `MYS`, `PHL`, `THI`, `IDO`, `LAT`

Region source fields (company level):

- Primary: `region_code`
- Fallback: `country`

Normalization behavior:

- Mapped aliases collapse into one CEO code.
- Unknown or unmapped values are assigned to `GKA`.
- Raw source values are retained in `source_region_values` for auditability.

## 5. Workflow Guardrails (Implemented)

Workflow: `.github/workflows/ceo-dashboard-hubspot-sync.yml`

Validation step fails run when any is true:

1. `metrics.company_totals.won_revenue_ytd <= 0`
2. `metrics.company_totals.next_90d_forecast <= 0`
3. Any `metrics.region_breakdown[*].region` outside CEO code set

## 6. Baseline Verification Snapshot

As-of date: `2026-03-22`  
Validated production values:

- `won_revenue_ytd = 1549224028.8`
- `qualified_pipeline = 58550912.68`
- `next_90d_forecast = 8598347.0`
- Region set: `CHN,GKA,IDO,LAT,MYS,PHL,SGP,THI`

## 7. Change Control

Changes requiring BizOps + RevOps + Data owner review:

- Won determination logic
- Next-90 fallback weighting logic
- Region normalization map
- Qualified stage selection logic
- Workflow guardrail thresholds or allowlist

Versioning rules:

- Any logic change increments spec version (`v1 -> v2`) and records effective date.
- Workflow validation and script implementation must be updated in the same change set.
