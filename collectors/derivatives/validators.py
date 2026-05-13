from __future__ import annotations

from typing import Any


def validate_investor_flow(rows: list[dict[str, Any]]) -> dict[str, Any]:
    required_categories = [
        "KOSPI200_FUTURES",
        "KOSPI200_CALL_OPTIONS",
        "KOSPI200_PUT_OPTIONS",
    ]
    errors: list[str] = []
    by_category = {row.get("category"): row for row in rows}

    for category in required_categories:
        row = by_category.get(category)
        if not row:
            errors.append(f"Missing required category: {category}")
            continue
        if row.get("foreigner_net_buy") is None:
            errors.append(f"{category}.foreigner_net_buy is null")
        if row.get("individual_net_buy") is None:
            errors.append(f"{category}.individual_net_buy is null")
        if row.get("institution_net_buy") is None:
            errors.append(f"{category}.institution_net_buy is null")
        if row.get("unit") != "억원":
            errors.append(f"{category}.unit is not '억원'")

    return {"valid": not errors, "errors": errors, "row_count": len(rows)}


def validate_market_index(rows: list[dict[str, Any]]) -> dict[str, Any]:
    required_names = ["KOSPI200", "KOSPI_FUTURES", "USDKRW"]
    errors: list[str] = []
    by_name = {row.get("standard_index_name"): row for row in rows}

    for name in required_names:
        row = by_name.get(name)
        if not row:
            errors.append(f"Missing required index: {name}")
            continue
        if row.get("current_value") is None:
            errors.append(f"{name}.current_value is null")

    return {"valid": not errors, "errors": errors, "row_count": len(rows)}


def validate_program_trading(rows: list[dict[str, Any]]) -> dict[str, Any]:
    required_pairs = [
        ("KOSPI", "ARBITRAGE"),
        ("KOSPI", "NON_ARBITRAGE"),
        ("KOSPI", "TOTAL"),
    ]
    errors: list[str] = []
    target_rows = {(row.get("market"), row.get("program_type")): row for row in rows}

    for key in required_pairs:
        row = target_rows.get(key)
        if not row:
            errors.append(f"Missing required market/program_type pair: {key[0]} {key[1]}")
            continue
        if row.get("net_buy_value") is None:
            errors.append(f"{key[0]} {key[1]} net_buy_value is null")

    return {"valid": not errors, "errors": errors, "row_count": len(rows)}
