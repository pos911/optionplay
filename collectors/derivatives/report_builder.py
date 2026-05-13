from __future__ import annotations

from pathlib import Path
from typing import Any

from .common import load_json, save_json, save_text


def _format_value(value: Any) -> str:
    if value is None:
        return "null"
    return str(value)


def _table(headers: list[str], rows: list[list[Any]]) -> str:
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join(["---"] * len(headers)) + " |"]
    for row in rows:
        lines.append("| " + " | ".join(_format_value(item) for item in row) + " |")
    return "\n".join(lines)


def build_derivatives_data_report(
    *,
    output_root: str | Path,
    trade_date: str,
    collection_results: list[dict[str, Any]],
    kis_auth_result: dict[str, Any] | None = None,
) -> dict[str, str]:
    root = Path(output_root)
    reports_dir = root / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    investor_payload = load_json(root / "data" / "raw" / f"kbsec_investor_trend_{trade_date.replace('-', '')}.json")
    index_payload = load_json(root / "data" / "raw" / f"kbsec_market_index_{trade_date.replace('-', '')}.json")
    program_payload = load_json(root / "data" / "raw" / f"hankyung_program_trading_{trade_date.replace('-', '')}.json")
    kis_futures_snapshot_payload = load_json(root / "data" / "raw" / f"kis_index_futures_snapshot_{trade_date.replace('-', '')}.json")
    kis_futures_daily_payload = load_json(root / "data" / "raw" / f"kis_index_futures_daily_{trade_date.replace('-', '')}.json")

    investor_rows = investor_payload.get("data", [])
    index_rows = index_payload.get("data", [])
    program_rows = program_payload.get("data", [])
    kis_futures_snapshot_rows = kis_futures_snapshot_payload.get("data", [])
    kis_futures_daily_rows = kis_futures_daily_payload.get("data", [])

    key_categories = {"KOSPI200_FUTURES", "KOSPI200_CALL_OPTIONS", "KOSPI200_PUT_OPTIONS"}
    key_investor_rows = [row for row in investor_rows if row.get("category") in key_categories]
    key_indices = {"KOSPI", "KOSDAQ", "KOSPI200", "KOSDAQ150", "KOSPI_FUTURES", "USDKRW", "NASDAQ", "SP500"}
    key_index_rows = [row for row in index_rows if row.get("standard_index_name") in key_indices]
    latest_program_rows = [
        row
        for row in program_rows
        if row.get("trade_date") == trade_date and row.get("market") == "KOSPI"
    ]

    summary_payload = {
        "trade_date": trade_date,
        "generated_from": [result.get("collector") for result in collection_results],
        "collection_status": collection_results,
        "kis_auth": kis_auth_result,
        "investor_flow_focus": key_investor_rows,
        "market_index_focus": key_index_rows,
        "program_trading_focus": latest_program_rows,
        "kis_futures_snapshot_focus": kis_futures_snapshot_rows,
        "kis_futures_daily_focus": kis_futures_daily_rows[:5],
        "notes": [
            "This bundle contains source data only.",
            "No investment opinion, market direction judgment, or forecast is included.",
            "Use these values as input to a later analysis step.",
        ],
    }

    md_lines = [
        "# Derivatives Market Data Packet",
        "",
        f"- trade_date: `{trade_date}`",
        f"- generated_at: `{investor_payload.get('collected_at') or index_payload.get('collected_at')}`",
        "- scope: `source data only`",
        "- interpretation: `not included`",
        "",
        "## Collection Status",
        "",
        _table(
            ["collector", "status", "row_count", "requests_success", "playwright_used", "error_message"],
            [
                [
                    result.get("collector"),
                    result.get("status"),
                    result.get("row_count"),
                    result.get("requests_success"),
                    result.get("playwright_used"),
                    result.get("error_message"),
                ]
                for result in collection_results
            ],
        ),
        "",
        "## KIS Auth Check",
        "",
        _table(
            ["status", "config_path", "base_url", "token_received", "expires_at", "error_message"],
            [
                [
                    (kis_auth_result or {}).get("status"),
                    (kis_auth_result or {}).get("config_path"),
                    (kis_auth_result or {}).get("base_url"),
                    (kis_auth_result or {}).get("token_received"),
                    (kis_auth_result or {}).get("expires_at"),
                    (kis_auth_result or {}).get("error_message"),
                ]
            ],
        ),
        "",
        "## KIS Futures Snapshot",
        "",
        _table(
            ["futures_code", "futures_name", "base_time", "base_time_source", "market_session", "current_price", "basis", "market_basis", "open_interest", "open_interest_change", "kospi200_index_value", "token_source"],
            [
                [
                    row.get("futures_code"),
                    row.get("futures_name"),
                    row.get("base_time"),
                    row.get("base_time_source"),
                    row.get("market_session"),
                    row.get("current_price"),
                    row.get("basis"),
                    row.get("market_basis"),
                    row.get("open_interest"),
                    row.get("open_interest_change"),
                    row.get("kospi200_index_value"),
                    row.get("token_source"),
                ]
                for row in kis_futures_snapshot_rows
            ],
        ),
        "",
        "## Investor Flow Focus",
        "",
        _table(
            ["category", "foreigner_net_buy", "individual_net_buy", "institution_net_buy", "unit"],
            [
                [
                    row.get("category"),
                    row.get("foreigner_net_buy"),
                    row.get("individual_net_buy"),
                    row.get("institution_net_buy"),
                    row.get("unit"),
                ]
                for row in key_investor_rows
            ],
        ),
        "",
        "## Market Index Focus",
        "",
        _table(
            ["group_name", "index_name", "standard_index_name", "current_value", "change_value", "change_rate", "direction"],
            [
                [
                    row.get("group_name"),
                    row.get("index_name"),
                    row.get("standard_index_name"),
                    row.get("current_value"),
                    row.get("change_value"),
                    row.get("change_rate"),
                    row.get("direction"),
                ]
                for row in key_index_rows
            ],
        ),
        "",
        "## Program Trading Focus",
        "",
        _table(
            ["market", "program_type", "buy_value", "sell_value", "net_buy_value", "unit_value"],
            [
                [
                    row.get("market"),
                    row.get("program_type"),
                    row.get("buy_value"),
                    row.get("sell_value"),
                    row.get("net_buy_value"),
                    row.get("unit_value"),
                ]
                for row in latest_program_rows
            ],
        ),
        "",
        "## KIS Futures Daily",
        "",
        _table(
            ["trade_date", "futures_code", "open_price", "high_price", "low_price", "close_price", "accumulated_volume", "accumulated_trading_value"],
            [
                [
                    row.get("trade_date"),
                    row.get("futures_code"),
                    row.get("open_price"),
                    row.get("high_price"),
                    row.get("low_price"),
                    row.get("close_price"),
                    row.get("accumulated_volume"),
                    row.get("accumulated_trading_value"),
                ]
                for row in kis_futures_daily_rows[:5]
            ],
        ),
        "",
        "## LLM Input Block",
        "",
        "```json",
        save_json.__globals__["json"].dumps(summary_payload, ensure_ascii=False, indent=2),
        "```",
        "",
    ]

    md_path = reports_dir / f"derivatives_market_data_report_{trade_date.replace('-', '')}.md"
    json_path = reports_dir / f"derivatives_market_data_packet_{trade_date.replace('-', '')}.json"
    txt_path = reports_dir / f"derivatives_market_llm_input_{trade_date.replace('-', '')}.txt"

    save_text(md_path, "\n".join(md_lines))
    save_json(json_path, summary_payload)
    save_text(
        txt_path,
        "\n".join(
            [
                "DERIVATIVES MARKET DATA INPUT",
                f"trade_date={trade_date}",
                "This file contains source data only. Do not assume any market interpretation is already applied.",
                save_json.__globals__["json"].dumps(summary_payload, ensure_ascii=False, indent=2),
            ]
        ),
    )

    return {
        "markdown_report": str(md_path),
        "json_packet": str(json_path),
        "llm_input_text": str(txt_path),
    }
