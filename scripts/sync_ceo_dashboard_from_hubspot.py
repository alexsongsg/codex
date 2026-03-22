#!/usr/bin/env python3
"""
Sync CEO Dashboard commercial metrics from HubSpot.

MVP focus:
- Pull Deals / Companies / Owners / Pipelines
- Produce normalized source payload
- Derive initial CEO commercial metrics (non-finance recognized revenue)
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


HUBSPOT_API_BASE = "https://api.hubapi.com"


class HubSpotApiError(RuntimeError):
    pass


def http_json(
    method: str,
    url: str,
    token: str,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json; charset=utf-8",
    }
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url=url, method=method, headers=headers, data=data)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            body = resp.read().decode("utf-8")
    except Exception as exc:
        raise HubSpotApiError(f"HTTP request failed: {method} {url} -> {exc}") from exc
    try:
        parsed = json.loads(body)
    except json.JSONDecodeError as exc:
        raise HubSpotApiError(f"Non-JSON response from HubSpot: {body[:300]}") from exc
    if isinstance(parsed, dict) and parsed.get("status") == "error":
        raise HubSpotApiError(
            f"HubSpot API error: {parsed.get('message', 'unknown')}, category={parsed.get('category')}"
        )
    return parsed


def parse_number(value: Any) -> float:
    if value in (None, ""):
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace(",", "")
    if not text:
        return 0.0
    try:
        return float(text)
    except ValueError:
        return 0.0


def parse_hs_datetime(value: Any) -> dt.datetime | None:
    if value in (None, ""):
        return None
    text = str(value).strip()
    for fmt in (
        "%Y-%m-%dT%H:%M:%S.%fZ",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%d",
    ):
        try:
            parsed = dt.datetime.strptime(text, fmt)
            if fmt == "%Y-%m-%d":
                parsed = dt.datetime.combine(parsed.date(), dt.time.min)
            return parsed.replace(tzinfo=dt.timezone.utc)
        except ValueError:
            continue
    # HubSpot may return epoch millis
    try:
        millis = int(float(text))
        return dt.datetime.fromtimestamp(millis / 1000.0, tz=dt.timezone.utc)
    except ValueError:
        return None


def iso_utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def parse_csv_list(text: str | None) -> list[str]:
    if not text:
        return []
    return [x.strip() for x in text.split(",") if x.strip()]


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def write_json(path: Path, payload: dict[str, Any]) -> None:
    ensure_parent(path)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def append_history_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    ensure_parent(path)
    file_exists = path.exists()
    fields = [
        "synced_at_utc",
        "as_of_date",
        "metric_name",
        "metric_scope",
        "value",
        "currency",
    ]
    with path.open("a", newline="", encoding="utf-8") as fp:
        writer = csv.DictWriter(fp, fieldnames=fields)
        if not file_exists:
            writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fields})


def paged_get_objects(
    token: str,
    object_name: str,
    properties: list[str],
    associations: list[str] | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    after: str | None = None
    while True:
        params: list[tuple[str, str]] = [("limit", str(limit))]
        for p in properties:
            params.append(("properties", p))
        if associations:
            for assoc in associations:
                params.append(("associations", assoc))
        if after:
            params.append(("after", after))
        query = urllib.parse.urlencode(params, doseq=True)
        url = f"{HUBSPOT_API_BASE}/crm/v3/objects/{object_name}?{query}"
        data = http_json("GET", url, token=token)
        batch = data.get("results", []) or []
        results.extend(batch)
        paging = data.get("paging", {})
        after = paging.get("next", {}).get("after")
        if not after:
            break
    return results


def get_owners(token: str) -> list[dict[str, Any]]:
    owners: list[dict[str, Any]] = []
    after: str | None = None
    while True:
        params = {"limit": 100}
        if after:
            params["after"] = after
        query = urllib.parse.urlencode(params)
        url = f"{HUBSPOT_API_BASE}/crm/v3/owners/?{query}"
        data = http_json("GET", url, token=token)
        batch = data.get("results", []) or []
        owners.extend(batch)
        after = data.get("paging", {}).get("next", {}).get("after")
        if not after:
            break
    return owners


def get_deal_pipelines(token: str) -> list[dict[str, Any]]:
    url = f"{HUBSPOT_API_BASE}/crm/v3/pipelines/deals"
    data = http_json("GET", url, token=token)
    return data.get("results", []) or []


def build_owner_map(owners: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for owner in owners:
        key = str(owner.get("id", ""))
        if key:
            out[key] = owner
    return out


def build_pipeline_stage_maps(
    pipelines: list[dict[str, Any]],
) -> tuple[dict[str, dict[str, Any]], set[str], set[str]]:
    stage_map: dict[str, dict[str, Any]] = {}
    won_stages: set[str] = set()
    closed_stages: set[str] = set()
    for p in pipelines:
        for s in p.get("stages", []) or []:
            sid = str(s.get("id", ""))
            if not sid:
                continue
            stage_map[sid] = s
            metadata = s.get("metadata", {}) or {}
            is_won = str(metadata.get("isWon", "")).lower() == "true"
            probability = metadata.get("probability")
            if is_won:
                won_stages.add(sid)
            if probability == "1.0" or str(metadata.get("isClosed", "")).lower() == "true":
                closed_stages.add(sid)
    return stage_map, won_stages, closed_stages


def pick_company_id_from_deal(deal: dict[str, Any]) -> str | None:
    assoc = deal.get("associations", {}) or {}
    companies = assoc.get("companies", {}) or {}
    results = companies.get("results", []) or []
    if not results:
        return None
    cid = results[0].get("id")
    return str(cid) if cid is not None else None


def load_region_targets(path: str | None) -> dict[str, float]:
    if not path:
        return {}
    p = Path(path)
    if not p.exists():
        return {}
    raw = json.loads(p.read_text(encoding="utf-8"))
    out: dict[str, float] = {}
    for k, v in raw.items():
        out[str(k)] = parse_number(v)
    return out


def derive_metrics(
    deals: list[dict[str, Any]],
    company_map: dict[str, dict[str, Any]],
    owner_map: dict[str, dict[str, Any]],
    won_stages: set[str],
    qualified_stage_ids: set[str],
    as_of_date: dt.date,
    region_targets: dict[str, float],
    default_currency: str,
) -> dict[str, Any]:
    ytd_start = dt.datetime(as_of_date.year, 1, 1, tzinfo=dt.timezone.utc)
    ytd_end = dt.datetime.combine(as_of_date, dt.time.max, tzinfo=dt.timezone.utc)
    n90_end = dt.datetime.combine(as_of_date + dt.timedelta(days=90), dt.time.max, tzinfo=dt.timezone.utc)

    region_won_ytd: dict[str, float] = {}
    region_qualified_pipeline: dict[str, float] = {}
    region_n90_forecast: dict[str, float] = {}
    region_owner: dict[str, str] = {}

    for deal in deals:
        props = deal.get("properties", {}) or {}
        stage = str(props.get("dealstage", "") or "")
        amount = parse_number(props.get("amount"))
        close_dt = parse_hs_datetime(props.get("closedate"))
        owner_id = str(props.get("hubspot_owner_id", "") or "")

        company_id = pick_company_id_from_deal(deal)
        company = company_map.get(company_id or "", {})
        region = (
            str(company.get("properties", {}).get("region_code", "") or "").strip()
            or str(company.get("properties", {}).get("country", "") or "UNKNOWN").strip()
        )

        if owner_id and region not in region_owner:
            owner = owner_map.get(owner_id, {})
            region_owner[region] = owner.get("firstName", "") + " " + owner.get("lastName", "")
            region_owner[region] = region_owner[region].strip() or owner.get("email", "") or owner_id

        if stage in won_stages and close_dt and ytd_start <= close_dt <= ytd_end:
            region_won_ytd[region] = region_won_ytd.get(region, 0.0) + amount

        if stage in qualified_stage_ids:
            region_qualified_pipeline[region] = region_qualified_pipeline.get(region, 0.0) + amount
            if close_dt and close_dt <= n90_end and close_dt >= dt.datetime.combine(
                as_of_date, dt.time.min, tzinfo=dt.timezone.utc
            ):
                region_n90_forecast[region] = region_n90_forecast.get(region, 0.0) + amount

    region_pipeline_coverage: dict[str, float | None] = {}
    for region, pipeline_amt in region_qualified_pipeline.items():
        target = region_targets.get(region)
        if target and target != 0:
            region_pipeline_coverage[region] = round(pipeline_amt / target, 4)
        else:
            region_pipeline_coverage[region] = None

    region_rows: list[dict[str, Any]] = []
    all_regions = sorted(
        set(region_won_ytd.keys())
        | set(region_qualified_pipeline.keys())
        | set(region_n90_forecast.keys())
        | set(region_owner.keys())
    )
    for r in all_regions:
        region_rows.append(
            {
                "region": r,
                "won_revenue_ytd": round(region_won_ytd.get(r, 0.0), 2),
                "qualified_pipeline": round(region_qualified_pipeline.get(r, 0.0), 2),
                "next_90d_forecast": round(region_n90_forecast.get(r, 0.0), 2),
                "pipeline_coverage": region_pipeline_coverage.get(r),
                "region_owner": region_owner.get(r, ""),
            }
        )

    totals = {
        "won_revenue_ytd": round(sum(region_won_ytd.values()), 2),
        "qualified_pipeline": round(sum(region_qualified_pipeline.values()), 2),
        "next_90d_forecast": round(sum(region_n90_forecast.values()), 2),
    }

    history_rows = [
        {
            "as_of_date": as_of_date.isoformat(),
            "metric_name": "HubSpot Won Revenue YTD (Commercial)",
            "metric_scope": "company",
            "value": totals["won_revenue_ytd"],
            "currency": default_currency,
        },
        {
            "as_of_date": as_of_date.isoformat(),
            "metric_name": "HubSpot Qualified Pipeline (Commercial)",
            "metric_scope": "company",
            "value": totals["qualified_pipeline"],
            "currency": default_currency,
        },
        {
            "as_of_date": as_of_date.isoformat(),
            "metric_name": "HubSpot Next 90-Day Forecast (Commercial)",
            "metric_scope": "company",
            "value": totals["next_90d_forecast"],
            "currency": default_currency,
        },
    ]

    return {
        "totals": totals,
        "regions": region_rows,
        "history_rows": history_rows,
    }


def build_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sync CEO Dashboard commercial layer from HubSpot")
    parser.add_argument("--hubspot-token", default=os.getenv("HUBSPOT_PRIVATE_APP_TOKEN"))
    parser.add_argument("--as-of-date", default=dt.date.today().isoformat())
    parser.add_argument("--currency", default=os.getenv("CEO_DASHBOARD_CURRENCY", "USD"))
    parser.add_argument(
        "--qualified-stage-ids",
        default=os.getenv("HUBSPOT_QUALIFIED_STAGE_IDS", ""),
        help="Comma-separated HubSpot dealstage IDs that count as qualified pipeline",
    )
    parser.add_argument(
        "--region-targets-json",
        default=os.getenv("HUBSPOT_REGION_TARGETS_JSON", ""),
        help="Optional JSON file path: {\"REGION\": number}",
    )
    parser.add_argument(
        "--output-json",
        default="reports/ceo_dashboard/hubspot_source_latest.json",
    )
    parser.add_argument(
        "--history-csv",
        default="reports/ceo_dashboard/hubspot_metrics_history.csv",
    )
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = build_args()
    if not args.hubspot_token:
        print("Missing required token: HUBSPOT_PRIVATE_APP_TOKEN", file=sys.stderr)
        return 2

    try:
        as_of = dt.date.fromisoformat(args.as_of_date)
    except ValueError:
        print(f"Invalid --as-of-date: {args.as_of_date}", file=sys.stderr)
        return 2

    qualified_stage_ids = set(parse_csv_list(args.qualified_stage_ids))
    region_targets = load_region_targets(args.region_targets_json)

    deal_props = [
        "dealname",
        "amount",
        "dealstage",
        "pipeline",
        "closedate",
        "createdate",
        "hs_lastmodifieddate",
        "hubspot_owner_id",
        "forecast_category",
        "hs_forecast_probability",
        "dealtype",
    ]
    company_props = [
        "name",
        "domain",
        "country",
        "region_code",
        "segment",
        "hubspot_owner_id",
    ]

    warnings: list[str] = []
    try:
        deals = paged_get_objects(
            token=args.hubspot_token,
            object_name="deals",
            properties=deal_props,
            associations=["companies"],
        )
    except HubSpotApiError as exc:
        print(f"HubSpot sync failed (deals is required): {exc}", file=sys.stderr)
        return 1

    try:
        companies = paged_get_objects(
            token=args.hubspot_token,
            object_name="companies",
            properties=company_props,
            associations=None,
        )
    except HubSpotApiError as exc:
        companies = []
        warnings.append(
            f"companies read failed; continue with UNKNOWN region fallback. detail={exc}"
        )

    try:
        owners = get_owners(token=args.hubspot_token)
    except HubSpotApiError as exc:
        owners = []
        warnings.append(f"owners read failed; continue without owner names. detail={exc}")

    try:
        pipelines = get_deal_pipelines(token=args.hubspot_token)
    except HubSpotApiError as exc:
        print(f"HubSpot sync failed (pipelines is required): {exc}", file=sys.stderr)
        return 1

    owner_map = build_owner_map(owners)
    stage_map, won_stages, closed_stages = build_pipeline_stage_maps(pipelines)
    if not qualified_stage_ids:
        # fallback for first-time onboarding:
        # use all stages that are not closed.
        qualified_stage_ids = {sid for sid in stage_map.keys() if sid not in closed_stages}

    company_map = {str(c.get("id", "")): c for c in companies if c.get("id") is not None}
    derived = derive_metrics(
        deals=deals,
        company_map=company_map,
        owner_map=owner_map,
        won_stages=won_stages,
        qualified_stage_ids=qualified_stage_ids,
        as_of_date=as_of,
        region_targets=region_targets,
        default_currency=args.currency,
    )

    synced_at = iso_utc_now()
    for row in derived["history_rows"]:
        row["synced_at_utc"] = synced_at

    payload = {
        "dashboard": "CEO Dashboard",
        "source": "hubspot",
        "version": "v1",
        "generated_at_utc": synced_at,
        "as_of_date": as_of.isoformat(),
        "accessed_objects": {
            "deals": len(deals),
            "companies": len(companies),
            "owners": len(owners),
            "pipelines": len(pipelines),
        },
        "config": {
            "qualified_stage_ids": sorted(qualified_stage_ids),
            "region_targets_json": args.region_targets_json or None,
        },
        "metrics": {
            "company_totals": derived["totals"],
            "region_breakdown": derived["regions"],
        },
        "notes": [
            "Commercial metrics from HubSpot are not finance recognized revenue.",
            "Revenue Actual YTD remains from Lark/Finance source chain.",
        ]
        + warnings,
    }

    if args.dry_run:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    output_json = Path(args.output_json)
    history_csv = Path(args.history_csv)
    write_json(output_json, payload)
    append_history_csv(history_csv, derived["history_rows"])

    print(json.dumps(payload, ensure_ascii=False, indent=2))
    print(f"Wrote JSON: {output_json}")
    print(f"Updated history: {history_csv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
