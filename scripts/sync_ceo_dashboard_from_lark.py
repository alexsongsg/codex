#!/usr/bin/env python3
"""
Sync CEO Dashboard source data from Lark Sheet.

P0 goal:
- Keep "Revenue Actual YTD" auto-updated from the designated Lark Sheet.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import os
import re
import sys
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any


LARK_API_BASE = "https://open.feishu.cn/open-apis"


class LarkApiError(RuntimeError):
    pass


@dataclass
class A1Window:
    start_row: int
    start_col: int
    end_row: int
    end_col: int


def env_or_arg(value: str | None, env_name: str) -> str | None:
    if value:
        return value
    return os.getenv(env_name)


def http_json(
    method: str,
    url: str,
    headers: dict[str, str] | None = None,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    data = None
    merged_headers = {"Content-Type": "application/json; charset=utf-8"}
    if headers:
        merged_headers.update(headers)
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url=url, method=method, headers=merged_headers, data=data)
    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            body = resp.read().decode("utf-8")
    except Exception as exc:
        raise LarkApiError(f"HTTP request failed: {method} {url} -> {exc}") from exc
    try:
        parsed = json.loads(body)
    except json.JSONDecodeError as exc:
        raise LarkApiError(f"Non-JSON response from {url}: {body[:300]}") from exc
    if parsed.get("code", 0) != 0:
        raise LarkApiError(
            f"Lark API error {parsed.get('code')}: {parsed.get('msg', 'unknown')}"
        )
    return parsed


def fetch_tenant_access_token(app_id: str, app_secret: str) -> str:
    url = f"{LARK_API_BASE}/auth/v3/tenant_access_token/internal"
    payload = {"app_id": app_id, "app_secret": app_secret}
    result = http_json("POST", url, payload=payload)
    token = result.get("tenant_access_token")
    if not token:
        raise LarkApiError("Missing tenant_access_token in auth response")
    return token


def fetch_sheet_range(
    tenant_access_token: str,
    spreadsheet_token: str,
    sheet_range: str,
) -> list[list[Any]]:
    encoded_range = urllib.parse.quote(sheet_range, safe="")
    url = f"{LARK_API_BASE}/sheets/v2/spreadsheets/{spreadsheet_token}/values/{encoded_range}"
    headers = {"Authorization": f"Bearer {tenant_access_token}"}
    result = http_json("GET", url, headers=headers)
    return result.get("data", {}).get("valueRange", {}).get("values", []) or []


def parse_number(value: Any) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    if value is None:
        raise ValueError("empty numeric value")
    text = str(value).strip()
    if not text:
        raise ValueError("empty numeric value")
    # strip common non-numeric characters (currency symbols, commas, spaces)
    cleaned = re.sub(r"[^\d.\-]", "", text)
    if cleaned in {"", "-", ".", "-."}:
        raise ValueError(f"invalid numeric value: {value}")
    return float(cleaned)


def col_letters_to_num(col: str) -> int:
    num = 0
    for ch in col.upper():
        if not ("A" <= ch <= "Z"):
            raise ValueError(f"invalid column letters: {col}")
        num = num * 26 + (ord(ch) - ord("A") + 1)
    return num


def parse_a1_cell_ref(ref: str) -> tuple[int, int]:
    match = re.fullmatch(r"\$?([A-Za-z]+)\$?(\d+)", ref.strip())
    if not match:
        raise ValueError(f"invalid A1 cell ref: {ref}")
    col_letters, row_num = match.group(1), match.group(2)
    return int(row_num), col_letters_to_num(col_letters)


def parse_a1_window(a1_range: str) -> A1Window:
    target = a1_range.strip()
    if "!" in target:
        target = target.split("!", 1)[1]
    if ":" in target:
        start_ref, end_ref = target.split(":", 1)
    else:
        start_ref = target
        end_ref = target
    start_row, start_col = parse_a1_cell_ref(start_ref)
    end_row, end_col = parse_a1_cell_ref(end_ref)
    if end_row < start_row or end_col < start_col:
        raise ValueError(f"invalid A1 range order: {a1_range}")
    return A1Window(
        start_row=start_row,
        start_col=start_col,
        end_row=end_row,
        end_col=end_col,
    )


def matrix_value_at_a1(values: list[list[Any]], window: A1Window, row: int, col: int) -> Any:
    row_idx = row - window.start_row
    col_idx = col - window.start_col
    if row_idx < 0 or col_idx < 0:
        return None
    if row_idx >= len(values):
        return None
    if col_idx >= len(values[row_idx]):
        return None
    return values[row_idx][col_idx]


def eval_sum_formula(
    formula: str,
    values: list[list[Any]],
    window: A1Window,
    depth: int = 0,
) -> float:
    match = re.fullmatch(r"\s*=\s*SUM\((.+)\)\s*", formula, re.I)
    if not match:
        raise ValueError(f"unsupported formula in numeric field: {formula}")
    args_text = match.group(1)
    total = 0.0
    for token in [x.strip() for x in args_text.split(",") if x.strip()]:
        if ":" in token:
            start_ref, end_ref = token.split(":", 1)
            start_row, start_col = parse_a1_cell_ref(start_ref)
            end_row, end_col = parse_a1_cell_ref(end_ref)
            if end_row < start_row or end_col < start_col:
                raise ValueError(f"invalid SUM range token: {token}")
            for r in range(start_row, end_row + 1):
                for c in range(start_col, end_col + 1):
                    raw = matrix_value_at_a1(values, window, r, c)
                    if raw in ("", None):
                        continue
                    raw = maybe_eval_formula_number(raw, values=values, window=window, depth=depth + 1)
                    total += parse_number(raw)
            continue
        # token can be a single cell ref or a numeric literal
        try:
            row, col = parse_a1_cell_ref(token)
            raw = matrix_value_at_a1(values, window, row, col)
            if raw not in ("", None):
                raw = maybe_eval_formula_number(raw, values=values, window=window, depth=depth + 1)
                total += parse_number(raw)
            continue
        except ValueError:
            pass
        total += parse_number(token)
    return total


def normalize_formula_text(raw: str) -> str:
    normalized = raw.lstrip()
    if normalized.startswith("'"):
        normalized = normalized[1:].lstrip()
    if normalized.upper().startswith("SUM("):
        normalized = "=" + normalized
    return normalized


def maybe_eval_formula_number(
    raw: Any,
    values: list[list[Any]],
    window: A1Window | None,
    depth: int = 0,
) -> Any:
    if window is None or not isinstance(raw, str):
        return raw
    if depth > 8:
        raise ValueError("formula evaluation exceeded recursion limit")
    normalized = normalize_formula_text(raw)
    if not normalized.startswith("="):
        return raw
    return eval_sum_formula(normalized, values=values, window=window, depth=depth + 1)


def parse_date(value: Any) -> dt.date:
    if isinstance(value, dt.date):
        return value
    text = str(value).strip()
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%d/%m/%Y", "%m/%d/%Y", "%Y.%m.%d"):
        try:
            return dt.datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"unsupported date format: {value}")


@dataclass
class SyncResult:
    metric_name: str
    value: float
    as_of_date: str
    currency: str
    source_type: str
    source_ref: str
    synced_at_utc: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "metric_name": self.metric_name,
            "value": self.value,
            "as_of_date": self.as_of_date,
            "currency": self.currency,
            "source_type": self.source_type,
            "source_ref": self.source_ref,
            "synced_at_utc": self.synced_at_utc,
        }


def compute_from_cell(values: list[list[Any]]) -> float:
    if not values or not values[0]:
        raise ValueError("cell returned empty value")
    return parse_number(values[0][0])


def compute_from_table(
    values: list[list[Any]],
    date_column: str,
    amount_column: str,
    as_of_date: dt.date,
) -> float:
    if len(values) < 2:
        raise ValueError("table range must include header and data rows")
    header = [str(x).strip() for x in values[0]]
    if date_column not in header or amount_column not in header:
        raise ValueError(
            f"columns not found. expected date='{date_column}', amount='{amount_column}', header={header}"
        )
    date_idx = header.index(date_column)
    amount_idx = header.index(amount_column)
    ytd_start = dt.date(as_of_date.year, 1, 1)
    total = 0.0
    for row in values[1:]:
        if date_idx >= len(row) or amount_idx >= len(row):
            continue
        raw_date = row[date_idx]
        raw_amount = row[amount_idx]
        if raw_date in ("", None) or raw_amount in ("", None):
            continue
        try:
            row_date = parse_date(raw_date)
            row_amount = parse_number(raw_amount)
        except ValueError:
            continue
        if ytd_start <= row_date <= as_of_date:
            total += row_amount
    return total


MONTH_NAME_TO_NUM = {
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
}


def compute_from_recognized_finals_row(
    values: list[list[Any]],
    row_label_column: str,
    row_label_value: str,
    as_of_date: dt.date,
    table_window: A1Window | None = None,
) -> float:
    if len(values) < 2:
        raise ValueError("recognized table range must include header and data rows")

    header = [str(x).strip() for x in values[0]]
    if row_label_column not in header:
        raise ValueError(f"row label column not found: {row_label_column}, header={header}")
    row_label_idx = header.index(row_label_column)

    target_row: list[Any] | None = None
    for row in values[1:]:
        if row_label_idx >= len(row):
            continue
        if str(row[row_label_idx]).strip().lower() == row_label_value.strip().lower():
            target_row = row
            break
    if target_row is None:
        raise ValueError(f"row label value not found: {row_label_value}")

    # Sum "Mon Final" columns up to as_of month, e.g. Jan Final + Feb Final.
    total = 0.0
    found_any_month_final = False
    for idx, col_name in enumerate(header):
        match = re.match(r"^(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+Final$", col_name, re.I)
        if not match:
            continue
        month_num = MONTH_NAME_TO_NUM[match.group(1).lower()]
        if month_num > as_of_date.month:
            continue
        if idx >= len(target_row):
            continue
        raw = target_row[idx]
        if raw in ("", None):
            continue
        raw = maybe_eval_formula_number(raw, values=values, window=table_window)
        found_any_month_final = True
        total += parse_number(raw)

    if not found_any_month_final:
        raise ValueError(
            "no monthly '* Final' columns found for current as-of month in recognized table"
        )
    return total


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def write_json(path: Path, payload: dict[str, Any]) -> None:
    ensure_parent(path)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def append_history_csv(path: Path, row: SyncResult) -> None:
    ensure_parent(path)
    file_exists = path.exists()
    with path.open("a", newline="", encoding="utf-8") as fp:
        writer = csv.writer(fp)
        if not file_exists:
            writer.writerow(
                [
                    "metric_name",
                    "value",
                    "as_of_date",
                    "currency",
                    "source_type",
                    "source_ref",
                    "synced_at_utc",
                ]
            )
        writer.writerow(
            [
                row.metric_name,
                f"{row.value:.2f}",
                row.as_of_date,
                row.currency,
                row.source_type,
                row.source_ref,
                row.synced_at_utc,
            ]
        )


def build_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Sync CEO Dashboard source from Lark Sheet (P0: Revenue Actual YTD)"
    )
    parser.add_argument("--metric-name", default="Revenue Actual YTD")
    parser.add_argument("--currency", default=os.getenv("CEO_DASHBOARD_CURRENCY", "USD"))
    parser.add_argument(
        "--mode",
        choices=["cell", "aggregate", "recognized_finals"],
        default="recognized_finals",
    )
    parser.add_argument("--output-json", default="reports/ceo_dashboard/source_latest.json")
    parser.add_argument(
        "--history-csv", default="reports/ceo_dashboard/revenue_actual_ytd_history.csv"
    )
    parser.add_argument("--as-of-date", default=dt.date.today().isoformat())

    parser.add_argument("--lark-app-id")
    parser.add_argument("--lark-app-secret")
    parser.add_argument("--spreadsheet-token")
    parser.add_argument("--sheet-id")
    parser.add_argument("--cell", default=os.getenv("LARK_REVENUE_CELL", "B2"))
    parser.add_argument("--table-range", default=os.getenv("LARK_REVENUE_TABLE_RANGE", "A1:Z5000"))
    parser.add_argument("--date-column", default=os.getenv("LARK_REVENUE_DATE_COLUMN", "Date"))
    parser.add_argument("--amount-column", default=os.getenv("LARK_REVENUE_AMOUNT_COLUMN", "Revenue"))
    parser.add_argument(
        "--recognized-row-label-column",
        default=os.getenv("LARK_RECOGNIZED_ROW_LABEL_COLUMN", "Team"),
    )
    parser.add_argument(
        "--recognized-row-label-value",
        default=os.getenv("LARK_RECOGNIZED_ROW_LABEL_VALUE", "All Countries"),
    )

    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = build_args()
    try:
        as_of = dt.date.fromisoformat(args.as_of_date)
    except ValueError:
        print(f"Invalid --as-of-date: {args.as_of_date}", file=sys.stderr)
        return 2

    app_id = env_or_arg(args.lark_app_id, "LARK_APP_ID")
    app_secret = env_or_arg(args.lark_app_secret, "LARK_APP_SECRET")
    spreadsheet_token = env_or_arg(args.spreadsheet_token, "LARK_SPREADSHEET_TOKEN")
    sheet_id = env_or_arg(args.sheet_id, "LARK_SHEET_ID")

    missing = []
    if not app_id:
        missing.append("LARK_APP_ID")
    if not app_secret:
        missing.append("LARK_APP_SECRET")
    if not spreadsheet_token:
        missing.append("LARK_SPREADSHEET_TOKEN")
    if not sheet_id:
        missing.append("LARK_SHEET_ID")
    if missing:
        print(f"Missing required config: {', '.join(missing)}", file=sys.stderr)
        return 2

    try:
        token = fetch_tenant_access_token(app_id=app_id, app_secret=app_secret)
        if args.mode == "cell":
            target_range = f"{sheet_id}!{args.cell}"
            values = fetch_sheet_range(token, spreadsheet_token, target_range)
            metric_value = compute_from_cell(values)
            source_ref = f"{spreadsheet_token}/{target_range}"
        elif args.mode == "aggregate":
            target_range = f"{sheet_id}!{args.table_range}"
            values = fetch_sheet_range(token, spreadsheet_token, target_range)
            metric_value = compute_from_table(
                values,
                date_column=args.date_column,
                amount_column=args.amount_column,
                as_of_date=as_of,
            )
            source_ref = (
                f"{spreadsheet_token}/{target_range}"
                f" (date={args.date_column}, amount={args.amount_column})"
            )
        else:
            target_range = f"{sheet_id}!{args.table_range}"
            values = fetch_sheet_range(token, spreadsheet_token, target_range)
            table_window = parse_a1_window(args.table_range)
            metric_value = compute_from_recognized_finals_row(
                values=values,
                row_label_column=args.recognized_row_label_column,
                row_label_value=args.recognized_row_label_value,
                as_of_date=as_of,
                table_window=table_window,
            )
            source_ref = (
                f"{spreadsheet_token}/{target_range}"
                f" (row={args.recognized_row_label_value}, column={args.recognized_row_label_column}, "
                f"rule='sum Mon Final <= as_of_month')"
            )
    except (LarkApiError, ValueError) as exc:
        print(f"Sync failed: {exc}", file=sys.stderr)
        return 1

    synced_at_utc = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()
    result = SyncResult(
        metric_name=args.metric_name,
        value=round(metric_value, 2),
        as_of_date=as_of.isoformat(),
        currency=args.currency,
        source_type="lark_sheet",
        source_ref=source_ref,
        synced_at_utc=synced_at_utc,
    )

    payload = {
        "dashboard": "CEO Dashboard",
        "version": "v1",
        "generated_at_utc": synced_at_utc,
        "metrics": [result.to_dict()],
    }

    if args.dry_run:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    output_json = Path(args.output_json)
    history_csv = Path(args.history_csv)
    write_json(output_json, payload)
    append_history_csv(history_csv, result)

    print(json.dumps(payload, ensure_ascii=False, indent=2))
    print(f"Wrote JSON: {output_json}")
    print(f"Updated history: {history_csv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
