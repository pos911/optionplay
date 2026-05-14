from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from collectors.derivatives import (
    HankyungProgramTradingCollector,
    KISAuthProbe,
    KISIndexFuturesCollector,
    KBSECInvestorTrendCollector,
    KBSECMarketIndexCollector,
    build_derivatives_data_report,
)
from collectors.derivatives.common import (
    VALID_TARGET_SLOTS,
    build_run_context,
    build_slot_suffix,
    current_timestamp,
    resolve_target_slot_for_timestamp,
    setup_logger,
)


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Collect derivatives market source data.")
    parser.add_argument(
        "--trade-date",
        default=date.today().isoformat(),
        help="Trade date label for saved files when the source page does not expose it explicitly.",
    )
    parser.add_argument(
        "--target-slot",
        default=None,
        help="Target slot in KST HHMM format. If omitted, the script derives it from the current KST time.",
    )
    parser.add_argument(
        "--output-root",
        default=".",
        help="Workspace root where data/, debug/, and logs/ directories live.",
    )
    parser.add_argument(
        "--api-keys-path",
        default=None,
        help="Optional api_keys.json path. If omitted, the script auto-discovers it.",
    )
    parser.add_argument(
        "--force-overwrite",
        action="store_true",
        help="Overwrite an existing target slot output set instead of skipping.",
    )
    return parser


def resolve_requested_target_slot(explicit_target_slot: str | None, collected_at: str) -> str:
    if explicit_target_slot:
        normalized = explicit_target_slot.replace(":", "")
        if normalized not in VALID_TARGET_SLOTS:
            raise ValueError(f"Invalid target_slot: {explicit_target_slot}")
        return normalized
    resolved = resolve_target_slot_for_timestamp(collected_at)
    if resolved is None:
        raise ValueError("Current KST time is outside the allowed target_slot retry window.")
    return resolved


def build_output_paths(output_root: Path, trade_date: str, target_slot: str) -> dict[str, Path]:
    suffix = build_slot_suffix(trade_date, target_slot)
    return {
        "log_path": output_root / "logs" / f"derivatives_data_collector_{suffix}.log",
        "markdown_report": output_root / "reports" / f"derivatives_market_data_report_{suffix}.md",
        "json_packet": output_root / "reports" / f"derivatives_market_data_packet_{suffix}.json",
        "llm_input_text": output_root / "reports" / f"derivatives_market_llm_input_{suffix}.txt",
    }


def should_skip_existing_outputs(output_paths: dict[str, Path], force_overwrite: bool) -> bool:
    if force_overwrite:
        return False
    return any(path.exists() for path in output_paths.values() if path.name.startswith("derivatives_market_"))


def main() -> int:
    args = build_argument_parser().parse_args()
    output_root = Path(args.output_root)
    collected_at = current_timestamp()
    target_slot = resolve_requested_target_slot(args.target_slot, collected_at)
    output_paths = build_output_paths(output_root, args.trade_date, target_slot)

    if should_skip_existing_outputs(output_paths, args.force_overwrite):
        run_context = build_run_context(trade_date=args.trade_date, target_slot=target_slot, collected_at=collected_at)
        summary = {
            "status": "skipped",
            "skip_reason": "slot already collected",
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
            "results": [],
            "kis_auth": {},
            "report_files": {key: str(value) for key, value in output_paths.items() if key != "log_path"},
            "report_status": None,
            "one_line_judgement": None,
            "composite_derivatives_score": None,
            "data_quality_warnings": [],
            "log_path": str(output_paths["log_path"]),
        }
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0

    logger = setup_logger(output_paths["log_path"])
    run_context = build_run_context(trade_date=args.trade_date, target_slot=target_slot, collected_at=collected_at)

    collectors = [
        KBSECInvestorTrendCollector(output_root=output_root, logger=logger),
        KBSECMarketIndexCollector(output_root=output_root, logger=logger),
        HankyungProgramTradingCollector(output_root=output_root, logger=logger),
    ]

    results: list[dict[str, object]] = []
    for collector in collectors:
        logger.info("Starting collector: %s", collector.__class__.__name__)
        result = collector.collect(trade_date=run_context.trade_date, target_slot=run_context.target_slot, collected_at=run_context.collected_at)
        results.append(result)
        logger.info(
            "Finished collector=%s status=%s rows=%s",
            result["collector"],
            result["status"],
            result["row_count"],
        )

    kis_probe = KISAuthProbe(output_root=output_root)
    try:
        kis_auth_result = kis_probe.verify(args.api_keys_path)
        logger.info("KIS auth probe status=%s", kis_auth_result.get("status"))
    except Exception as exc:
        kis_auth_result = {
            "status": "failed",
            "error_message": str(exc),
            "config_path": args.api_keys_path,
        }
        logger.error("KIS auth probe failed: %s", exc)

    kis_futures_collector = KISIndexFuturesCollector(output_root=output_root, logger=logger)
    logger.info("Starting collector: %s", kis_futures_collector.__class__.__name__)
    kis_futures_result = kis_futures_collector.collect(
        trade_date=run_context.trade_date,
        target_slot=run_context.target_slot,
        api_keys_path=args.api_keys_path,
        collected_at=run_context.collected_at,
    )
    results.append(kis_futures_result)
    logger.info(
        "Finished collector=%s status=%s rows=%s",
        kis_futures_result["collector"],
        kis_futures_result["status"],
        kis_futures_result["row_count"],
    )

    report_files = build_derivatives_data_report(
        output_root=output_root,
        trade_date=run_context.trade_date,
        target_slot=run_context.target_slot,
        collected_at=run_context.collected_at,
        collection_results=results,
        kis_auth_result=kis_auth_result,
    )

    summary = {
        "status": "success",
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
        "results": results,
        "kis_auth": kis_auth_result,
        "report_files": report_files,
        "report_status": report_files.get("report_status"),
        "one_line_judgement": report_files.get("one_line_judgement"),
        "composite_derivatives_score": report_files.get("composite_derivatives_score"),
        "data_quality_warnings": report_files.get("data_quality_warnings", []),
        "log_path": str(output_paths["log_path"]),
    }
    all_failed = all(result["status"] != "success" for result in results)
    kis_failed = kis_futures_result["status"] != "success"
    partial_failed = any(result["status"] != "success" for result in results)
    if all_failed or kis_failed:
        summary["status"] = "failed"
    elif partial_failed:
        summary["status"] = "warn"
    logger.info("Collection summary: %s", json.dumps(summary, ensure_ascii=False))
    print(json.dumps(summary, ensure_ascii=False, indent=2))

    if all_failed or kis_failed:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
