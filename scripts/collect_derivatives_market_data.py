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
    KISIndexFuturesCollector,
    KISAuthProbe,
    KBSECInvestorTrendCollector,
    KBSECMarketIndexCollector,
    build_derivatives_data_report,
)
from collectors.derivatives.common import setup_logger


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Collect derivatives market source data.")
    parser.add_argument(
        "--trade-date",
        default=date.today().isoformat(),
        help="Trade date label for saved files when the source page does not expose it explicitly.",
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
    return parser


def main() -> int:
    args = build_argument_parser().parse_args()
    output_root = Path(args.output_root)
    log_path = output_root / "logs" / f"derivatives_data_collector_{args.trade_date.replace('-', '')}.log"
    logger = setup_logger(log_path)

    collectors = [
        KBSECInvestorTrendCollector(output_root=output_root, logger=logger),
        KBSECMarketIndexCollector(output_root=output_root, logger=logger),
        HankyungProgramTradingCollector(output_root=output_root, logger=logger),
    ]

    results: list[dict[str, object]] = []
    for collector in collectors:
        logger.info("Starting collector: %s", collector.__class__.__name__)
        result = collector.collect(trade_date=args.trade_date)
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
    kis_futures_result = kis_futures_collector.collect(trade_date=args.trade_date, api_keys_path=args.api_keys_path)
    results.append(kis_futures_result)
    logger.info(
        "Finished collector=%s status=%s rows=%s",
        kis_futures_result["collector"],
        kis_futures_result["status"],
        kis_futures_result["row_count"],
    )

    report_files = build_derivatives_data_report(
        output_root=output_root,
        trade_date=args.trade_date,
        collection_results=results,
        kis_auth_result=kis_auth_result,
    )

    summary = {
        "trade_date": args.trade_date,
        "results": results,
        "kis_auth": kis_auth_result,
        "report_files": report_files,
        "log_path": str(log_path),
    }
    logger.info("Collection summary: %s", json.dumps(summary, ensure_ascii=False))
    print(json.dumps(summary, ensure_ascii=False, indent=2))

    if any(result["status"] != "success" for result in results):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
