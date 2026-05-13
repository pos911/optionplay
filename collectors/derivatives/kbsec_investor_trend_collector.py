from __future__ import annotations

import logging
from io import StringIO
from pathlib import Path
from typing import Any

import pandas as pd

from .common import (
    PLAYWRIGHT_USER_AGENT,
    PLAYWRIGHT_VIEWPORT,
    compute_raw_hash,
    create_requests_session,
    current_timestamp,
    decode_euc_kr_response,
    extract_text_lines,
    normalize_signed_number,
    normalize_trade_date,
    normalize_whitespace,
    payload_with_status,
    respectful_get,
    save_csv,
    save_json,
    save_text,
    time_fields_for_row,
)
from .validators import validate_investor_flow

URL = "https://m.kbsec.com/go.able?linkcd=m05040000"
SOURCE = "KBSEC"

CATEGORY_MAP = {
    "코스피": "KOSPI",
    "코스닥": "KOSDAQ",
    "코스피200 선물": "KOSPI200_FUTURES",
    "코스피200 콜옵션": "KOSPI200_CALL_OPTIONS",
    "코스피200 풋옵션": "KOSPI200_PUT_OPTIONS",
    "미니 선물": "MINI_FUTURES",
    "미니 콜옵션": "MINI_CALL_OPTIONS",
    "미니 풋옵션": "MINI_PUT_OPTIONS",
}


class KBSECInvestorTrendCollector:
    url = URL
    source = SOURCE

    def __init__(self, output_root: str | Path = ".", logger: logging.Logger | None = None) -> None:
        self.output_root = Path(output_root)
        self.logger = logger or logging.getLogger(__name__)

    @staticmethod
    def map_category(label: str) -> str | None:
        return CATEGORY_MAP.get(normalize_whitespace(label))

    def parse_with_pandas(self, html_text: str, trade_date: str, collected_at: str) -> list[dict[str, Any]]:
        dataframes = pd.read_html(StringIO(html_text))
        rows: list[dict[str, Any]] = []
        for dataframe in dataframes:
            if "구분" not in dataframe.columns.tolist():
                continue
            for _, series in dataframe.iterrows():
                raw_label = normalize_whitespace(series.iloc[0])
                category = self.map_category(raw_label)
                if not category:
                    continue
                rows.append(
                    {
                        "trade_date": trade_date,
                        "category": category,
                        "foreigner_net_buy": normalize_signed_number(series.iloc[1] if len(series) > 1 else None),
                        "individual_net_buy": normalize_signed_number(series.iloc[2] if len(series) > 2 else None),
                        "institution_net_buy": normalize_signed_number(series.iloc[3] if len(series) > 3 else None),
                        "unit": "억원",
                        "source": self.source,
                        "source_url": self.url,
                        "collected_at": collected_at,
                        "raw_hash": compute_raw_hash(html_text),
                        **time_fields_for_row(collected_at=collected_at),
                    }
                )
        return rows

    def parse_with_text(self, html_text: str, trade_date: str, collected_at: str) -> list[dict[str, Any]]:
        lines = extract_text_lines(html_text)
        start_index = 0
        if "기관계" in lines:
            start_index = lines.index("기관계") + 1

        rows: list[dict[str, Any]] = []
        index = start_index
        while index < len(lines):
            token = lines[index]
            label = token
            if token in {"코스피200", "미니"} and index + 1 < len(lines):
                next_token = lines[index + 1]
                combined = f"{token} {next_token}"
                if combined in CATEGORY_MAP:
                    label = combined
                    index += 1
            category = self.map_category(label)
            if not category:
                index += 1
                continue
            values = lines[index + 1 : index + 4]
            if len(values) < 3:
                break
            rows.append(
                {
                    "trade_date": trade_date,
                    "category": category,
                    "foreigner_net_buy": normalize_signed_number(values[0]),
                    "individual_net_buy": normalize_signed_number(values[1]),
                    "institution_net_buy": normalize_signed_number(values[2]),
                    "unit": "억원",
                    "source": self.source,
                    "source_url": self.url,
                    "collected_at": collected_at,
                    "raw_hash": compute_raw_hash(html_text),
                    **time_fields_for_row(collected_at=collected_at),
                }
            )
            index += 4
        return rows

    def _playwright_fallback(self, debug_dir: Path) -> dict[str, str]:
        artifacts: dict[str, str] = {}
        try:
            from playwright.sync_api import sync_playwright

            screenshot_path = debug_dir / "screenshots" / "kbsec_investor_trend.png"
            html_path = debug_dir / "kbsec_investor_trend_playwright.html"
            text_path = debug_dir / "kbsec_investor_trend_playwright.txt"
            network_path = debug_dir / "network" / "kbsec_investor_trend_network.json"

            responses: list[dict[str, Any]] = []
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                context = browser.new_context(
                    user_agent=PLAYWRIGHT_USER_AGENT,
                    viewport=PLAYWRIGHT_VIEWPORT,
                    is_mobile=True,
                )
                page = context.new_page()
                page.on(
                    "response",
                    lambda response: responses.append(
                        {
                            "url": response.url,
                            "status": response.status,
                            "resource_type": response.request.resource_type,
                        }
                    ),
                )
                page.goto(self.url, wait_until="networkidle", timeout=30000)
                save_text(html_path, page.content())
                save_text(text_path, page.locator("body").inner_text())
                page.screenshot(path=str(screenshot_path), full_page=True)
                browser.close()

            save_json(network_path, responses)
            artifacts.update(
                {
                    "playwright_html": str(html_path),
                    "playwright_text": str(text_path),
                    "screenshot": str(screenshot_path),
                    "network_log": str(network_path),
                }
            )
        except Exception as exc:
            self.logger.warning("Playwright fallback failed for KBSEC investor trend: %s", exc)
        return artifacts

    def collect(self, trade_date: str | None = None) -> dict[str, Any]:
        session = create_requests_session()
        collected_at = current_timestamp()
        normalized_trade_date = normalize_trade_date(trade_date)

        debug_dir = self.output_root / "debug"
        raw_dir = self.output_root / "data" / "raw"
        html_debug_path = debug_dir / "kbsec_investor_trend_raw.html"
        text_debug_path = debug_dir / "kbsec_investor_trend_parsed.txt"
        json_path = raw_dir / f"kbsec_investor_trend_{normalized_trade_date.replace('-', '')}.json"
        csv_path = raw_dir / f"kbsec_investor_trend_{normalized_trade_date.replace('-', '')}.csv"

        rows: list[dict[str, Any]] = []
        artifacts: dict[str, str] = {}
        error_message: str | None = None

        try:
            fetch_result = respectful_get(session, self.url, self.logger, expect_euc_kr=True)
            html_text = decode_euc_kr_response(fetch_result.response)
            content_type = fetch_result.response.headers.get("content-type", "")
            if "euc-kr" not in content_type.lower().replace("_", "-"):
                self.logger.warning("Unexpected content-type for KBSEC investor trend: %s", content_type)
            artifacts["raw_html"] = save_text(html_debug_path, html_text)

            try:
                rows = self.parse_with_pandas(html_text, normalized_trade_date, collected_at)
                self.logger.info("KBSEC investor trend parsed with pandas: %s rows", len(rows))
            except Exception as exc:
                self.logger.warning("pandas parsing failed for KBSEC investor trend: %s", exc)

            if not rows:
                rows = self.parse_with_text(html_text, normalized_trade_date, collected_at)
                artifacts["parsed_text"] = save_text(text_debug_path, "\n".join(extract_text_lines(html_text)))
                self.logger.info("KBSEC investor trend parsed with text fallback: %s rows", len(rows))

            validation = validate_investor_flow(rows)
            status = "success" if validation["valid"] else "failed"
            if not validation["valid"]:
                error_message = "; ".join(validation["errors"])
                artifacts.update(self._playwright_fallback(debug_dir))
                if "parsed_text" not in artifacts:
                    artifacts["parsed_text"] = save_text(text_debug_path, "\n".join(extract_text_lines(html_text)))
            payload = payload_with_status(
                trade_date=normalized_trade_date,
                collected_at=collected_at,
                source=self.source,
                source_url=self.url,
                data=rows,
                status=status,
                error_message=error_message,
                validation=validation,
            )
            artifacts["json"] = save_json(json_path, payload)
            artifacts["csv"] = save_csv(
                csv_path,
                rows,
                [
                    "trade_date",
                    "base_time",
                    "base_time_source",
                    "source_time",
                    "market_session",
                    "category",
                    "foreigner_net_buy",
                    "individual_net_buy",
                    "institution_net_buy",
                    "unit",
                    "source",
                    "source_url",
                    "collected_at",
                    "raw_hash",
                ],
            )
            return {
                "collector": "kbsec_investor_trend",
                "status": status,
                "row_count": len(rows),
                "validation": validation,
                "files": artifacts,
                "requests_success": True,
                "playwright_used": status == "failed" and "screenshot" in artifacts,
                "error_message": error_message,
                "source_url": self.url,
            }
        except Exception as exc:
            error_message = str(exc)
            artifacts.update(self._playwright_fallback(debug_dir))
            payload = payload_with_status(
                trade_date=normalized_trade_date,
                collected_at=collected_at,
                source=self.source,
                source_url=self.url,
                data=[],
                status="failed",
                error_message=error_message,
                validation={"valid": False, "errors": [error_message], "row_count": 0},
            )
            artifacts["json"] = save_json(json_path, payload)
            artifacts["csv"] = save_csv(
                csv_path,
                [],
                [
                    "trade_date",
                    "base_time",
                    "base_time_source",
                    "source_time",
                    "market_session",
                    "category",
                    "foreigner_net_buy",
                    "individual_net_buy",
                    "institution_net_buy",
                    "unit",
                    "source",
                    "source_url",
                    "collected_at",
                    "raw_hash",
                ],
            )
            self.logger.error("KBSEC investor trend collection failed: %s", exc)
            return {
                "collector": "kbsec_investor_trend",
                "status": "failed",
                "row_count": 0,
                "validation": {"valid": False, "errors": [error_message], "row_count": 0},
                "files": artifacts,
                "requests_success": False,
                "playwright_used": "screenshot" in artifacts,
                "error_message": error_message,
                "source_url": self.url,
            }
