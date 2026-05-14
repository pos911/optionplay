from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .common import build_run_context, build_slot_suffix, load_json, next_target_slot, save_json, save_text, slot_to_hhmm


def _format_value(value: Any) -> str:
    return "null" if value is None else str(value)


def _table(headers: list[str], rows: list[list[Any]]) -> str:
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join(["---"] * len(headers)) + " |"]
    for row in rows:
        lines.append("| " + " | ".join(_format_value(item) for item in row) + " |")
    return "\n".join(lines)


def _clamp(value: int, low: int, high: int) -> int:
    return max(low, min(high, value))


def _load_rules(root: Path) -> dict[str, Any]:
    candidates = [
        root / "config" / "derivatives_report_rules.json",
        Path(__file__).resolve().parents[2] / "config" / "derivatives_report_rules.json",
    ]
    for candidate in candidates:
        if candidate.exists():
            return json.loads(candidate.read_text(encoding="utf-8"))
    raise FileNotFoundError("derivatives_report_rules.json not found")


def _eval_op(left: float, op: str, right: float) -> bool:
    if op == ">=":
        return left >= right
    if op == "<=":
        return left <= right
    if op == ">":
        return left > right
    if op == "<":
        return left < right
    if op == "==":
        return left == right
    raise ValueError(f"Unsupported operator: {op}")


def _score_from_rules(metrics: dict[str, float], rules: list[dict[str, Any]]) -> tuple[int, list[str]]:
    score = 0
    reasons: list[str] = []
    for rule in rules:
        metric_value = float(metrics.get(rule["metric"], 0))
        if _eval_op(metric_value, rule["op"], float(rule["value"])):
            score += int(rule["score"])
            reasons.append(rule["label"])
    return score, reasons


def _row_by_key(rows: list[dict[str, Any]], key: str, value: str) -> dict[str, Any]:
    return next((row for row in rows if row.get(key) == value), {})


def _program_row(rows: list[dict[str, Any]], program_type: str) -> dict[str, Any]:
    return next((row for row in rows if row.get("market") == "KOSPI" and row.get("program_type") == program_type), {})


def _to_number(value: Any) -> float:
    if value in {None, ""}:
        return 0.0
    return float(value)


def _fmt_pct(value: Any) -> str:
    if value in {None, ""}:
        return "데이터 없음"
    return f"{float(value):.2f}%"


def _fmt_value_or_missing(value: Any) -> str:
    return "미수집" if value in {None, ""} else str(value)


def _build_metrics(
    investor_rows: list[dict[str, Any]],
    index_rows: list[dict[str, Any]],
    program_rows: list[dict[str, Any]],
    futures_rows: list[dict[str, Any]],
) -> dict[str, float]:
    futures = _row_by_key(investor_rows, "category", "KOSPI200_FUTURES")
    call_options = _row_by_key(investor_rows, "category", "KOSPI200_CALL_OPTIONS")
    put_options = _row_by_key(investor_rows, "category", "KOSPI200_PUT_OPTIONS")
    fx = _row_by_key(index_rows, "standard_index_name", "USDKRW")
    futures_snapshot = futures_rows[0] if futures_rows else {}

    return {
        "foreigner_net_buy": _to_number(futures.get("foreigner_net_buy")),
        "institution_net_buy": _to_number(futures.get("institution_net_buy")),
        "individual_net_buy": _to_number(futures.get("individual_net_buy")),
        "open_interest_change": _to_number(futures_snapshot.get("open_interest_change")),
        "basis_minus_market_basis": _to_number(futures_snapshot.get("basis")) - _to_number(futures_snapshot.get("market_basis")),
        "program_total_net_buy": _to_number(_program_row(program_rows, "TOTAL").get("net_buy_value")),
        "program_non_arbitrage_net_buy": _to_number(_program_row(program_rows, "NON_ARBITRAGE").get("net_buy_value")),
        "usdkrw_change_rate": _to_number(fx.get("change_rate")),
        "foreigner_call_net_buy": _to_number(call_options.get("foreigner_net_buy")),
        "foreigner_put_net_buy": _to_number(put_options.get("foreigner_net_buy")),
        "foreign_call_buy_put_sell_signal": 1.0
        if _to_number(call_options.get("foreigner_net_buy")) > 0 and _to_number(put_options.get("foreigner_net_buy")) < 0
        else 0.0,
        "foreign_call_sell_put_buy_signal": 1.0
        if _to_number(call_options.get("foreigner_net_buy")) < 0 and _to_number(put_options.get("foreigner_net_buy")) > 0
        else 0.0,
    }


def _build_scores(metrics: dict[str, float], rules: dict[str, Any]) -> dict[str, Any]:
    futures_flow_score, futures_reasons = _score_from_rules(metrics, rules["futures_flow_rules"])
    options_flow_score, options_reasons = _score_from_rules(metrics, rules["options_flow_rules"])
    program_flow_score, program_reasons = _score_from_rules(metrics, rules["program_flow_rules"])
    fx_risk_score, fx_reasons = _score_from_rules(metrics, rules["fx_risk_rules"])
    composite = _clamp(futures_flow_score + options_flow_score + program_flow_score + fx_risk_score, -10, 10)
    return {
        "futures_flow_score": _clamp(futures_flow_score, -5, 5),
        "options_flow_score": _clamp(options_flow_score, -5, 5),
        "program_flow_score": _clamp(program_flow_score, -5, 5),
        "fx_risk_score": _clamp(fx_risk_score, -5, 5),
        "composite_derivatives_score": composite,
        "score_reasons": {
            "futures": futures_reasons,
            "options": options_reasons,
            "program": program_reasons,
            "fx": fx_reasons,
        },
    }


def _build_report_status(schedule_lag_minutes: int) -> str:
    if schedule_lag_minutes >= 60:
        return "STALE_TEST_RUN"
    if schedule_lag_minutes >= 16:
        return "DELAYED_LIVE"
    return "LIVE"


def _build_kospi_futures_semantics(index_rows: list[dict[str, Any]]) -> dict[str, Any]:
    kospi_futures = _row_by_key(index_rows, "standard_index_name", "KOSPI_FUTURES")
    if not kospi_futures:
        return {
            "available": False,
            "semantics_confirmed": False,
            "score_included": False,
            "note": "KOSPI_FUTURES row was not collected.",
        }

    source_code = kospi_futures.get("source_code")
    inferred_product = None
    if source_code == "A0166000":
        inferred_product = "KBSEC market page label KOSPI선물, detail link gbn=FUT, realtime feed KBRSFFC0"

    return {
        "available": True,
        "source_code": source_code,
        "index_name": kospi_futures.get("index_name"),
        "raw_current_value_text": kospi_futures.get("raw_current_value_text"),
        "raw_change_text": kospi_futures.get("raw_change_text"),
        "current_value": kospi_futures.get("current_value"),
        "change_value": kospi_futures.get("change_value"),
        "change_rate": kospi_futures.get("change_rate"),
        "direction": kospi_futures.get("direction"),
        "inferred_product": inferred_product,
        "semantics_confirmed": False,
        "score_included": False,
        "note": "Source identifies this row as a futures item, but exact contract-month and change-rate semantics remain unconfirmed.",
    }


def _build_data_quality_warnings(index_rows: list[dict[str, Any]], collection_results: list[dict[str, Any]]) -> tuple[list[str], list[str], dict[str, Any]]:
    warnings: list[str] = []
    score_exclusions: list[str] = []
    index_result = next((result for result in collection_results if result.get("collector") == "kbsec_market_index"), {})
    if index_result.get("status") != "success":
        warnings.append("KBSEC 시장지수 수집 실패로 지수/환율 판단 신뢰도 낮음")

    kospi_futures_semantics = _build_kospi_futures_semantics(index_rows)
    kospi200 = _row_by_key(index_rows, "standard_index_name", "KOSPI200")
    kospi_futures = _row_by_key(index_rows, "standard_index_name", "KOSPI_FUTURES")
    k200_rate = kospi200.get("change_rate")
    fut_rate = kospi_futures.get("change_rate")
    if k200_rate not in {None, ""} and fut_rate not in {None, ""}:
        k200_rate = float(k200_rate)
        fut_rate = float(fut_rate)
        if abs(k200_rate) >= 0.5 and abs(fut_rate) >= 0.5 and (k200_rate > 0 > fut_rate or k200_rate < 0 < fut_rate):
            warnings.append(
                "KOSPI200 and KOSPI_FUTURES change_rate directions diverge sharply. Verify KOSPI_FUTURES field semantics before using as live confirmation."
            )
            score_exclusions.append("KOSPI_FUTURES change_rate excluded from score calculation because its semantics are unconfirmed under divergent direction.")
            kospi_futures_semantics["score_included"] = False
    return warnings, score_exclusions, kospi_futures_semantics


def _build_one_line_judgement(report_status: str, scores: dict[str, Any]) -> str:
    futures_score = scores["futures_flow_score"]
    options_score = scores["options_flow_score"]
    program_score = scores["program_flow_score"]
    composite = scores["composite_derivatives_score"]

    if report_status == "STALE_TEST_RUN":
        return "지연 수집으로 장중 판단에는 부적합하다. 이 결과는 backfill/test snapshot으로만 봐야 한다."

    prefix = "지연 수집: " if report_status == "DELAYED_LIVE" else ""

    if futures_score < 0 < program_score:
        return prefix + "선물 하방 압력과 프로그램 매수가 충돌하는 혼조 구간이다."
    if futures_score > 0 > program_score:
        return prefix + "선물 상방 압력과 프로그램 매도가 충돌하는 혼조 구간이다."

    signs = {0 if score == 0 else (1 if score > 0 else -1) for score in [futures_score, options_score, program_score]}
    non_zero_signs = {sign for sign in signs if sign != 0}
    if len(non_zero_signs) > 1:
        return prefix + "선물, 옵션, 프로그램 신호가 엇갈리는 혼조 구간이다."
    if composite > 0 and futures_score < 0:
        return prefix + "프로그램 매수로 외국인 선물 하방 압력이 일부 상쇄되는 구간이다."
    if composite < 0 and futures_score > 0:
        return prefix + "프로그램 매도로 외국인 선물 상방 압력이 일부 상쇄되는 구간이다."
    if composite > 0:
        return prefix + "파생 수급은 전반적으로 상방 우위다."
    if composite < 0:
        return prefix + "파생 수급은 전반적으로 하방 우위다."
    return prefix + "뚜렷한 우위 없이 혼조 구간이다."


def _build_interpretation(
    run_context: Any,
    report_status: str,
    investor_rows: list[dict[str, Any]],
    index_rows: list[dict[str, Any]],
    program_rows: list[dict[str, Any]],
    futures_rows: list[dict[str, Any]],
    scores: dict[str, Any],
    score_exclusions: list[str],
) -> dict[str, Any]:
    futures = _row_by_key(investor_rows, "category", "KOSPI200_FUTURES")
    call_options = _row_by_key(investor_rows, "category", "KOSPI200_CALL_OPTIONS")
    put_options = _row_by_key(investor_rows, "category", "KOSPI200_PUT_OPTIONS")
    kospi = _row_by_key(index_rows, "standard_index_name", "KOSPI")
    kosdaq = _row_by_key(index_rows, "standard_index_name", "KOSDAQ")
    kospi200 = _row_by_key(index_rows, "standard_index_name", "KOSPI200")
    kospi_futures = _row_by_key(index_rows, "standard_index_name", "KOSPI_FUTURES")
    usdkrw = _row_by_key(index_rows, "standard_index_name", "USDKRW")
    nasdaq = _row_by_key(index_rows, "standard_index_name", "NASDAQ")
    sp500 = _row_by_key(index_rows, "standard_index_name", "SP500")
    futures_snapshot = futures_rows[0] if futures_rows else {}
    arbitrage = _program_row(program_rows, "ARBITRAGE")
    non_arbitrage = _program_row(program_rows, "NON_ARBITRAGE")
    total = _program_row(program_rows, "TOTAL")
    next_slot = next_target_slot(run_context.target_slot)

    option_tone = "약상방 또는 혼조"
    if _to_number(call_options.get("foreigner_net_buy")) > 0 and _to_number(put_options.get("foreigner_net_buy")) < 0:
        option_tone = "상방 베팅"
    elif _to_number(call_options.get("foreigner_net_buy")) < 0 and _to_number(put_options.get("foreigner_net_buy")) > 0:
        option_tone = "하방 또는 헤지"

    futures_sentence = (
        f"외국인 선물 순매수는 {_fmt_value_or_missing(futures.get('foreigner_net_buy'))}, "
        f"미결제약정 변화는 {_fmt_value_or_missing(futures_snapshot.get('open_interest_change'))}, "
        f"basis는 {_fmt_value_or_missing(futures_snapshot.get('basis'))}, market_basis는 {_fmt_value_or_missing(futures_snapshot.get('market_basis'))}로 "
        f"선물 수급 점수는 {scores['futures_flow_score']}이다."
    )
    options_sentence = (
        f"외국인 콜 순매수는 {_fmt_value_or_missing(call_options.get('foreigner_net_buy'))}, "
        f"풋 순매수는 {_fmt_value_or_missing(put_options.get('foreigner_net_buy'))}로 "
        f"옵션 해석은 {option_tone}이며 옵션 점수는 {scores['options_flow_score']}이다."
    )
    program_sentence = (
        f"KOSPI 차익은 {_fmt_value_or_missing(arbitrage.get('net_buy_value'))}, "
        f"비차익은 {_fmt_value_or_missing(non_arbitrage.get('net_buy_value'))}, "
        f"전체는 {_fmt_value_or_missing(total.get('net_buy_value'))}로 프로그램 점수는 {scores['program_flow_score']}이다."
    )
    macro_sentence = (
        f"KOSPI {_fmt_pct(kospi.get('change_rate'))}, "
        f"KOSDAQ {_fmt_pct(kosdaq.get('change_rate'))}, "
        f"KOSPI200 {_fmt_pct(kospi200.get('change_rate'))}, "
        f"KOSPI futures {_fmt_pct(kospi_futures.get('change_rate'))}, "
        f"USDKRW {_fmt_pct(usdkrw.get('change_rate'))}, "
        f"NASDAQ {_fmt_pct(nasdaq.get('change_rate'))}, "
        f"SP500 {_fmt_pct(sp500.get('change_rate'))}. "
        f"환율 리스크 점수는 {scores['fx_risk_score']}이다."
    )
    if score_exclusions:
        macro_sentence += " " + " ".join(score_exclusions)

    return {
        "one_line_judgement": _build_one_line_judgement(report_status, scores),
        "futures_view": futures_sentence,
        "options_view": options_sentence,
        "program_view": program_sentence,
        "macro_view": macro_sentence,
        "next_checkpoint": (
            f"다음 체크포인트는 {slot_to_hhmm(next_slot) if next_slot else '장마감 이후'}다. "
            f"외국인 선물 방향 지속 여부, 비차익 강도 변화, 콜/풋 방향 전환 여부를 확인한다."
        ),
    }


def build_derivatives_data_report(
    *,
    output_root: str | Path,
    trade_date: str,
    target_slot: str,
    collected_at: str,
    collection_results: list[dict[str, Any]],
    kis_auth_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    root = Path(output_root)
    reports_dir = root / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    run_context = build_run_context(trade_date=trade_date, target_slot=target_slot, collected_at=collected_at)
    file_suffix = build_slot_suffix(trade_date, target_slot)
    report_status = _build_report_status(run_context.schedule_lag_minutes)

    investor_payload = load_json(root / "data" / "raw" / f"kbsec_investor_trend_{file_suffix}.json")
    index_payload = load_json(root / "data" / "raw" / f"kbsec_market_index_{file_suffix}.json")
    program_payload = load_json(root / "data" / "raw" / f"hankyung_program_trading_{file_suffix}.json")
    kis_futures_snapshot_payload = load_json(root / "data" / "raw" / f"kis_index_futures_snapshot_{file_suffix}.json")
    kis_futures_daily_payload = load_json(root / "data" / "raw" / f"kis_index_futures_daily_{file_suffix}.json")

    investor_rows = investor_payload.get("data", [])
    index_rows = index_payload.get("data", [])
    program_rows = program_payload.get("data", [])
    kis_futures_snapshot_rows = kis_futures_snapshot_payload.get("data", [])
    kis_futures_daily_rows = kis_futures_daily_payload.get("data", [])

    key_categories = {"KOSPI200_FUTURES", "KOSPI200_CALL_OPTIONS", "KOSPI200_PUT_OPTIONS"}
    key_investor_rows = [row for row in investor_rows if row.get("category") in key_categories]
    key_indices = {"KOSPI", "KOSDAQ", "KOSPI200", "KOSPI_FUTURES", "USDKRW", "NASDAQ", "SP500"}
    key_index_rows = [row for row in index_rows if row.get("standard_index_name") in key_indices]
    latest_program_rows = [row for row in program_rows if row.get("trade_date") == trade_date and row.get("market") == "KOSPI"]

    rules = _load_rules(root)
    metrics = _build_metrics(key_investor_rows, key_index_rows, latest_program_rows, kis_futures_snapshot_rows)
    scores = _build_scores(metrics, rules)
    data_quality_warnings, score_exclusions, kospi_futures_semantics = _build_data_quality_warnings(key_index_rows, collection_results)
    interpretation = _build_interpretation(
        run_context,
        report_status,
        key_investor_rows,
        key_index_rows,
        latest_program_rows,
        kis_futures_snapshot_rows,
        scores,
        score_exclusions,
    )

    warnings: list[str] = []
    if run_context.schedule_lag_minutes > 15:
        warnings.append(
            f"WARNING: This snapshot was collected {run_context.schedule_lag_minutes} minutes after "
            f"target_slot={run_context.target_slot}. Use as delayed snapshot, not exact {slot_to_hhmm(run_context.target_slot)} data."
        )
    warnings.extend(data_quality_warnings)

    summary_payload = {
        "trade_date": run_context.trade_date,
        "target_slot": run_context.target_slot,
        "generated_at": run_context.generated_at,
        "collected_at": run_context.collected_at,
        "actual_kst_time": run_context.actual_kst_time,
        "schedule_lag_minutes": run_context.schedule_lag_minutes,
        "market_session": run_context.market_session,
        "source_time": run_context.source_time,
        "base_time": run_context.base_time,
        "base_time_source": run_context.base_time_source,
        "report_status": report_status,
        "warning": "\n".join(warnings) if warnings else None,
        "data_quality_warnings": data_quality_warnings,
        "score_exclusions": score_exclusions,
        "generated_from": [result.get("collector") for result in collection_results],
        "collection_status": collection_results,
        "kis_auth": kis_auth_result,
        "scores": scores,
        "source_payloads": {
            "kbsec_market_index": index_payload,
            "kis_index_futures_snapshot": kis_futures_snapshot_payload,
        },
        "instrument_semantics": {
            "KOSPI_FUTURES": kospi_futures_semantics,
        },
        **interpretation,
        "investor_flow_focus": key_investor_rows,
        "market_index_focus": key_index_rows,
        "program_trading_focus": latest_program_rows,
        "kis_futures_snapshot_focus": kis_futures_snapshot_rows,
        "kis_futures_daily_focus": kis_futures_daily_rows[:5],
    }

    md_lines = [
        "# Derivatives Market Snapshot Report",
        "",
        *(["## Warning", "", *warnings, ""] if warnings else []),
        f"- trade_date: `{run_context.trade_date}`",
        f"- target_slot: `{run_context.target_slot}`",
        f"- actual_kst_time: `{run_context.actual_kst_time}`",
        f"- schedule_lag_minutes: `{run_context.schedule_lag_minutes}`",
        f"- report_status: `{report_status}`",
        "",
        "## 오늘의 파생시장 한줄판단",
        "",
        interpretation["one_line_judgement"],
        "",
        "## 판단 강도 점수",
        "",
        _table(
            ["score", "value"],
            [
                ["futures_flow_score", scores["futures_flow_score"]],
                ["options_flow_score", scores["options_flow_score"]],
                ["program_flow_score", scores["program_flow_score"]],
                ["fx_risk_score", scores["fx_risk_score"]],
                ["composite_derivatives_score", scores["composite_derivatives_score"]],
            ],
        ),
        "",
        "## 선물 수급 판단",
        "",
        interpretation["futures_view"],
        "",
        "## 옵션 수급 판단",
        "",
        interpretation["options_view"],
        "",
        "## 프로그램매매 판단",
        "",
        interpretation["program_view"],
        "",
        "## 지수 및 환율 환경",
        "",
        interpretation["macro_view"],
        "",
        "## 다음 슬롯 체크포인트",
        "",
        interpretation["next_checkpoint"],
        "",
        "## Data Quality Warnings",
        "",
        *(data_quality_warnings if data_quality_warnings else ["None"]),
        "",
        "## Score Exclusions",
        "",
        *(score_exclusions if score_exclusions else ["None"]),
        "",
        "## KOSPI_FUTURES Semantics",
        "",
        _table(
            ["field", "value"],
            [
                ["source_code", kospi_futures_semantics.get("source_code")],
                ["index_name", kospi_futures_semantics.get("index_name")],
                ["current_value", kospi_futures_semantics.get("current_value")],
                ["change_value", kospi_futures_semantics.get("change_value")],
                ["change_rate", _fmt_pct(kospi_futures_semantics.get("change_rate"))],
                ["raw_change_text", kospi_futures_semantics.get("raw_change_text")],
                ["inferred_product", kospi_futures_semantics.get("inferred_product")],
                ["semantics_confirmed", kospi_futures_semantics.get("semantics_confirmed")],
                ["score_included", kospi_futures_semantics.get("score_included")],
                ["note", kospi_futures_semantics.get("note")],
            ],
        ),
        "",
        "## Market Index Focus",
        "",
        _table(
            ["standard_index_name", "current_value", "change_rate", "direction", "source_code", "raw_change_text"],
            [
                [
                    row.get("standard_index_name"),
                    row.get("current_value"),
                    _fmt_pct(row.get("change_rate")),
                    row.get("direction"),
                    row.get("source_code"),
                    row.get("raw_change_text"),
                ]
                for row in key_index_rows
            ],
        ),
        "",
    ]

    md_path = reports_dir / f"derivatives_market_data_report_{file_suffix}.md"
    json_path = reports_dir / f"derivatives_market_data_packet_{file_suffix}.json"
    txt_path = reports_dir / f"derivatives_market_llm_input_{file_suffix}.txt"

    save_text(md_path, "\n".join(md_lines))
    save_json(json_path, summary_payload)
    save_text(
        txt_path,
        "\n".join(
            [
                "DERIVATIVES MARKET SNAPSHOT INPUT",
                f"trade_date={run_context.trade_date}",
                f"target_slot={run_context.target_slot}",
                f"report_status={report_status}",
                f"actual_kst_time={run_context.actual_kst_time}",
                f"composite_derivatives_score={scores['composite_derivatives_score']}",
                interpretation["one_line_judgement"],
                json.dumps(summary_payload, ensure_ascii=False, indent=2),
            ]
        ),
    )

    return {
        "markdown_report": str(md_path),
        "json_packet": str(json_path),
        "llm_input_text": str(txt_path),
        "report_status": report_status,
        "one_line_judgement": interpretation["one_line_judgement"],
        "composite_derivatives_score": scores["composite_derivatives_score"],
        "data_quality_warnings": data_quality_warnings,
    }
