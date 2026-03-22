#!/usr/bin/env python3
"""
Render a single-page CEO Dashboard index from Lark (finance) and HubSpot (commercial) sources.
"""

from __future__ import annotations

import argparse
import csv
import html
import json
from pathlib import Path
from typing import Any


def esc(v: Any) -> str:
    return html.escape(str(v if v is not None else ""))


def money(v: Any) -> str:
    if v in (None, "", "n/a"):
        return "N/A"
    try:
        return f"{float(v):,.2f}"
    except (TypeError, ValueError):
        return "N/A"


def read_json_if_exists(path: Path | None) -> dict[str, Any] | None:
    if not path or not path.exists():
        return None
    text = path.read_text(encoding="utf-8").lstrip("\ufeff")
    return json.loads(text)


def latest_lark_revenue(
    lark_json_path: Path | None,
    lark_history_csv_path: Path | None,
) -> tuple[Any, str, str]:
    # returns (value, as_of_date, source_note)
    payload = read_json_if_exists(lark_json_path)
    if payload:
        metrics = payload.get("metrics") or []
        if metrics and isinstance(metrics, list):
            row = metrics[0] or {}
            return (
                row.get("value"),
                str(row.get("as_of_date") or ""),
                "lark_json",
            )

    if lark_history_csv_path and lark_history_csv_path.exists():
        with lark_history_csv_path.open("r", encoding="utf-8", newline="") as fp:
            rows = list(csv.DictReader(fp))
        if rows:
            last = rows[-1]
            return (
                last.get("value"),
                str(last.get("as_of_date") or ""),
                "lark_history_csv",
            )

    return (None, "", "missing")


def hubspot_metrics(hubspot_json_path: Path | None) -> dict[str, Any]:
    payload = read_json_if_exists(hubspot_json_path)
    if not payload:
        return {
            "as_of_date": "",
            "generated_at_utc": "",
            "currency": "USD",
            "won_revenue_ytd": None,
            "qualified_pipeline": None,
            "next_90d_forecast": None,
            "regions": [],
        }
    totals = ((payload.get("metrics") or {}).get("company_totals") or {})
    return {
        "as_of_date": str(payload.get("as_of_date") or ""),
        "generated_at_utc": str(payload.get("generated_at_utc") or ""),
        "currency": str(payload.get("currency") or "USD"),
        "won_revenue_ytd": totals.get("won_revenue_ytd"),
        "qualified_pipeline": totals.get("qualified_pipeline"),
        "next_90d_forecast": totals.get("next_90d_forecast"),
        "regions": ((payload.get("metrics") or {}).get("region_breakdown") or []),
    }


def render_html(
    finance_value: Any,
    finance_as_of: str,
    finance_source: str,
    hubspot: dict[str, Any],
) -> str:
    region_rows = []
    for row in hubspot.get("regions", []) or []:
        region_rows.append(
            f"""
            <tr>
              <td>{esc(row.get("region", ""))}</td>
              <td class="num">{money(row.get("won_revenue_ytd"))}</td>
              <td class="num">{money(row.get("qualified_pipeline"))}</td>
              <td class="num">{money(row.get("next_90d_forecast"))}</td>
              <td>{esc(row.get("region_owner", ""))}</td>
            </tr>
            """.strip()
        )
    region_tbody = "\n".join(region_rows) if region_rows else '<tr><td colspan="5">No HubSpot region data</td></tr>'

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>CEO Dashboard - Finance + Commercial</title>
  <style>
    :root {{
      --bg: #f4f8fc;
      --surface: #ffffff;
      --ink: #10213c;
      --muted: #5f708a;
      --line: #d6e1ef;
      --accent1: #165d9c;
      --accent2: #0e7a4b;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: "Segoe UI", "Helvetica Neue", Arial, sans-serif;
      color: var(--ink);
      background: linear-gradient(135deg, #eef5ff 0%, var(--bg) 60%);
    }}
    .wrap {{ max-width: 1200px; margin: 0 auto; padding: 22px 14px 36px; }}
    h1 {{ margin: 0; font-size: 30px; }}
    .meta {{ color: var(--muted); margin-top: 8px; font-size: 13px; }}
    .grid {{
      margin-top: 16px;
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 12px;
    }}
    .panel {{
      background: var(--surface);
      border: 1px solid var(--line);
      border-radius: 12px;
      padding: 14px;
    }}
    .panel h2 {{ margin: 0 0 10px; font-size: 16px; }}
    .kpi-label {{ color: var(--muted); font-size: 12px; text-transform: uppercase; letter-spacing: .04em; }}
    .kpi-value {{ margin-top: 6px; font-size: 26px; font-weight: 700; color: var(--accent1); }}
    .stack {{ display: grid; grid-template-columns: repeat(3, minmax(0,1fr)); gap: 8px; }}
    .mini {{ border: 1px solid var(--line); border-radius: 10px; padding: 10px; }}
    .mini .v {{ margin-top: 5px; font-weight: 700; color: var(--accent2); font-size: 18px; }}
    .table-wrap {{ margin-top: 12px; background: var(--surface); border: 1px solid var(--line); border-radius: 12px; overflow: hidden; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
    th, td {{ border-bottom: 1px solid var(--line); padding: 10px; text-align: left; }}
    th {{ background: #f7fbff; }}
    .num {{ text-align: right; white-space: nowrap; font-variant-numeric: tabular-nums; }}
    @media (max-width: 900px) {{
      .grid {{ grid-template-columns: 1fr; }}
      .stack {{ grid-template-columns: 1fr; }}
    }}
  </style>
</head>
<body>
  <div class="wrap">
    <h1>CEO Dashboard</h1>
    <div class="meta">
      Finance as-of: {esc(finance_as_of or "N/A")} | HubSpot as-of: {esc(hubspot.get("as_of_date") or "N/A")} |
      HubSpot generated UTC: {esc(hubspot.get("generated_at_utc") or "N/A")}
    </div>

    <section class="grid">
      <article class="panel">
        <h2>Finance (Lark)</h2>
        <div class="kpi-label">Revenue Actual YTD</div>
        <div class="kpi-value">{money(finance_value)}</div>
        <div class="meta">Source: {esc(finance_source)}</div>
      </article>
      <article class="panel">
        <h2>Commercial (HubSpot)</h2>
        <div class="stack">
          <div class="mini">
            <div class="kpi-label">Won Revenue YTD</div>
            <div class="v">{money(hubspot.get("won_revenue_ytd"))}</div>
          </div>
          <div class="mini">
            <div class="kpi-label">Qualified Pipeline</div>
            <div class="v">{money(hubspot.get("qualified_pipeline"))}</div>
          </div>
          <div class="mini">
            <div class="kpi-label">Next 90d Forecast</div>
            <div class="v">{money(hubspot.get("next_90d_forecast"))}</div>
          </div>
        </div>
      </article>
    </section>

    <section class="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Region</th>
            <th class="num">Won Revenue YTD</th>
            <th class="num">Qualified Pipeline</th>
            <th class="num">Next 90d Forecast</th>
            <th>Region Owner</th>
          </tr>
        </thead>
        <tbody>
          {region_tbody}
        </tbody>
      </table>
    </section>
  </div>
</body>
</html>
"""


def build_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Render CEO Dashboard single page (Finance + Commercial)")
    p.add_argument("--lark-json", default="reports/ceo_dashboard/source_latest.json")
    p.add_argument("--lark-history-csv", default="reports/ceo_dashboard/revenue_actual_ytd_history.csv")
    p.add_argument("--hubspot-json", default="reports/ceo_dashboard/hubspot_source_latest.json")
    p.add_argument("--output", default="reports/ceo_dashboard/index.html")
    return p.parse_args()


def main() -> int:
    args = build_args()
    lark_json = Path(args.lark_json) if args.lark_json else None
    lark_csv = Path(args.lark_history_csv) if args.lark_history_csv else None
    hubspot_json = Path(args.hubspot_json) if args.hubspot_json else None

    finance_value, finance_as_of, finance_source = latest_lark_revenue(lark_json, lark_csv)
    hubspot = hubspot_metrics(hubspot_json)
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        render_html(finance_value, finance_as_of, finance_source, hubspot),
        encoding="utf-8",
    )
    print(f"Wrote HTML: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
