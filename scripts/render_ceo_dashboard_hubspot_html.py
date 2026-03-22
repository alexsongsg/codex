#!/usr/bin/env python3
"""
Render CEO Dashboard HubSpot HTML view from sync JSON payload.
"""

from __future__ import annotations

import argparse
import html
import json
from json import JSONDecoder
from pathlib import Path
from typing import Any


def parse_payload(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    text = text.lstrip("\ufeff")
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass

    decoder = JSONDecoder()
    for i, ch in enumerate(text):
        if ch != "{":
            continue
        try:
            data, _ = decoder.raw_decode(text[i:])
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            return data
    raise ValueError(f"Could not parse JSON payload from {path}")


def money(v: Any) -> str:
    try:
        num = float(v or 0)
    except (TypeError, ValueError):
        num = 0.0
    return f"{num:,.2f}"


def pct(v: Any) -> str:
    if v in (None, ""):
        return "-"
    try:
        num = float(v)
    except (TypeError, ValueError):
        return "-"
    return f"{num * 100:.2f}%"


def esc(v: Any) -> str:
    return html.escape(str(v if v is not None else ""))


def render(payload: dict[str, Any]) -> str:
    metrics = payload.get("metrics", {}) or {}
    totals = metrics.get("company_totals", {}) or {}
    regions = metrics.get("region_breakdown", []) or []
    currency = payload.get("currency") or "USD"
    as_of_date = payload.get("as_of_date", "")
    generated_at = payload.get("generated_at_utc", "")

    rows = []
    for row in regions:
        src_values = row.get("source_region_values") or []
        if isinstance(src_values, list):
            src = ", ".join(str(x) for x in src_values)
        else:
            src = str(src_values)
        rows.append(
            f"""
            <tr>
              <td>{esc(row.get("region", ""))}</td>
              <td class="num">{money(row.get("won_revenue_ytd"))}</td>
              <td class="num">{money(row.get("qualified_pipeline"))}</td>
              <td class="num">{money(row.get("next_90d_forecast"))}</td>
              <td class="num">{pct(row.get("pipeline_coverage"))}</td>
              <td>{esc(row.get("region_owner", ""))}</td>
              <td class="src">{esc(src)}</td>
            </tr>
            """.strip()
        )

    region_table = "\n".join(rows) if rows else '<tr><td colspan="7">No region data</td></tr>'

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>CEO Dashboard - HubSpot Commercial</title>
  <style>
    :root {{
      --bg: #f3f7fb;
      --surface: #ffffff;
      --ink: #0f1b2d;
      --muted: #5b6b82;
      --accent: #1264a3;
      --line: #d7e2ef;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: "Segoe UI", "Helvetica Neue", Arial, sans-serif;
      background: radial-gradient(circle at top right, #e6f1ff 0%, var(--bg) 55%);
      color: var(--ink);
    }}
    .wrap {{
      max-width: 1200px;
      margin: 0 auto;
      padding: 24px 16px 40px;
    }}
    .head {{
      margin-bottom: 16px;
    }}
    .title {{
      margin: 0;
      font-size: 28px;
      font-weight: 700;
    }}
    .sub {{
      margin-top: 6px;
      color: var(--muted);
      font-size: 14px;
    }}
    .cards {{
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 12px;
      margin: 16px 0 22px;
    }}
    .card {{
      background: var(--surface);
      border: 1px solid var(--line);
      border-radius: 12px;
      padding: 14px;
    }}
    .k {{
      color: var(--muted);
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 0.04em;
    }}
    .v {{
      margin-top: 8px;
      font-size: 24px;
      font-weight: 700;
      color: var(--accent);
    }}
    .table-wrap {{
      background: var(--surface);
      border: 1px solid var(--line);
      border-radius: 12px;
      overflow: hidden;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 13px;
    }}
    th, td {{
      border-bottom: 1px solid var(--line);
      padding: 10px 12px;
      text-align: left;
      vertical-align: top;
    }}
    th {{
      background: #f7fbff;
      color: #33415c;
      font-weight: 600;
    }}
    .num {{
      text-align: right;
      white-space: nowrap;
      font-variant-numeric: tabular-nums;
    }}
    .src {{
      color: #344860;
      min-width: 220px;
    }}
    @media (max-width: 900px) {{
      .cards {{ grid-template-columns: 1fr; }}
      table {{ font-size: 12px; }}
      th, td {{ padding: 8px; }}
    }}
  </style>
</head>
<body>
  <div class="wrap">
    <div class="head">
      <h1 class="title">CEO Dashboard - HubSpot Commercial</h1>
      <div class="sub">As of: {esc(as_of_date)} | Generated at (UTC): {esc(generated_at)} | Currency: {esc(currency)}</div>
    </div>

    <section class="cards">
      <article class="card">
        <div class="k">Won Revenue YTD</div>
        <div class="v">{money(totals.get("won_revenue_ytd"))}</div>
      </article>
      <article class="card">
        <div class="k">Qualified Pipeline</div>
        <div class="v">{money(totals.get("qualified_pipeline"))}</div>
      </article>
      <article class="card">
        <div class="k">Next 90d Forecast</div>
        <div class="v">{money(totals.get("next_90d_forecast"))}</div>
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
            <th class="num">Pipeline Coverage</th>
            <th>Region Owner</th>
            <th>Source Region Values</th>
          </tr>
        </thead>
        <tbody>
          {region_table}
        </tbody>
      </table>
    </section>
  </div>
</body>
</html>
"""


def build_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render CEO Dashboard HubSpot HTML")
    parser.add_argument("--input", required=True, help="Path to HubSpot sync JSON or sync output log")
    parser.add_argument("--output", required=True, help="Output HTML file")
    return parser.parse_args()


def main() -> int:
    args = build_args()
    src = Path(args.input)
    out = Path(args.output)
    payload = parse_payload(src)
    html_text = render(payload)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html_text, encoding="utf-8")
    print(f"Wrote HTML: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
