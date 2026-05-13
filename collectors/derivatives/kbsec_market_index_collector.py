from __future__ import annotations

import logging
import re
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
    parse_change_pair,
    payload_with_status,
    respectful_get,
    save_csv,
    save_json,
    save_text,
    time_fields_for_row,
)
from .validators import validate_market_index

URL = "https://m.kbsec.com/go.able?linkcd=m04040000"
SOURCE = "KBSEC"
GROUPS = ["DOMESTIC_INDEX", "GLOBAL_INDEX", "FX_COMMODITY"]
STANDARD_NAME_MAP = {
    "코스피 종합": "KOSPI",
    "코스닥 종합": "KOSDAQ",
    "코스피 200": "KOSPI200",
    "코스닥 150": "KOSDAQ150",
    "KOSPI선물": "KOSPI_FUTURES",
    "원/달러": "USDKRW",
    "나스닥 종합": "NASDAQ",
    "S&P 500": "SP500",
}


class KBSECMarketIndexCollector:
    url = URL
    source = SOURCE

    def __init__(self, output_root: str | Path = ".", logger: logging.Logger | None = None) -> None:
        self.output_root = Path(output_root)
        self.logger = logger or logging.getLogger(__name__)

    @staticmethod
    def standardize_index_name(name: str) -> str:
        return STANDARD_NAME_MAP.get(normalize_whitespace(name), normalize_whitespace(name))

    @staticmethod
    def extract_raw_note(html_text: str) -> str | None:
        match = re.search(r"15\s*~\s*20분 지연 또는 종가지수입니다\.", html_text)
        return match.group(0) if match else None

    def parse_with_pandas(self, html_text: str, trade_date: str, collected_at: str) -> list[dict[str, Any]]:
        note = self.extract_raw_note(html_text)
        rows: list[dict[str, Any]] = []
        for group_name, dataframe in zip(GROUPS, pd.read_html(StringIO(html_text))):
            for _, series in dataframe.iterrows():
                raw_name = normalize_whitespace(series.iloc[0])
                current_value = normalize_signed_number(series.iloc[1])
                change_value, change_rate, direction = parse_change_pair(series.iloc[2])
                rows.append(
                    {
                        "trade_date": trade_date,
                        "group_name": group_name,
                        "index_name": raw_name,
                        "standard_index_name": self.standardize_index_name(raw_name),
                        "current_value": current_value,
                        "change_value": change_value,
                        "change_rate": change_rate,
                        "direction": direction,
                        "unit": None,
                        "raw_note": note,
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
        note = self.extract_raw_note(html_text)
        section_headers = {
            "국내지수 정보": "DOMESTIC_INDEX",
            "해외지수 정보": "GLOBAL_INDEX",
            "환율/유가 정보": "FX_COMMODITY",
        }
        rows: list[dict[str, Any]] = []
        current_group: str | None = None
        index = 0
        while index < len(lines):
            token = lines[index]
            if token in section_headers:
                current_group = section_headers[token]
                index += 1
                continue
            if token == "15 ~ 20분 지연 또는 종가지수입니다.":
                index += 1
                continue
            if current_group and index + 2 < len(lines):
                raw_name = token
                current_value = normalize_signed_number(lines[index + 1])
                change_value, change_rate, direction = parse_change_pair(lines[index + 2])
                if current_value is not None and change_value is not None:
                    rows.append(
                        {
                            "trade_date": trade_date,
                            "group_name": current_group,
                            "index_name": raw_name,
                            "standard_index_name": self.standardize_index_name(raw_name),
                            "current_value": current_value,
                            "change_value": change_value,
                            "change_rate": change_rate,
                            "direction": direction,
                            "unit": None,
                            "raw_note": note,
                            "source": self.source,
                            "source_url": self.url,
                            "collected_at": collected_at,
                            "raw_hash": compute_raw_hash(html_text),
                            **time_fields_for_row(collected_at=collected_at),
                        }
                    )
                    index += 3
                    continue
            index += 1
        return rows

    def _playwright_fallback(self, debug_dir: Path) -> dict[str, str]:
        artifacts: dict[str, str] = {}
        try:
            from playwright.sync_api import sync_playwright

            screenshot_path = debug_dir / "screenshots" / "kbsec_market_index.png"
            html_path = debug_dir / "kbsec_market_index_playwright.html"
            text_path = debug_dir / "kbsec_market_index_playwright.txt"
            network_path = debug_dir / "network" / "kbsec_market_index_network.json"

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
            self.logger.warning("Playwright fallback failed for KBSEC market index: %s", exc)
        return artifacts

    def collect(self, trade_date: str | None = None) -> dict[str, Any]:
        session = create_requests_session()
        collected_at = current_timestamp()
        normalized_trade_date = normalize_trade_date(trade_date)

        debug_dir = self.output_root / "debug"
        raw_dir = self.output_root / "data" / "raw"
        html_debug_path = debug_dir / "kbsec_market_index_raw.html"
        text_debug_path = debug_dir / "kbsec_market_index_parsed.txt"
        json_path = raw_dir / f"kbsec_market_index_{normalized_trade_date.replace('-', '')}.json"
        csv_path = raw_dir / f"kbsec_market_index_{normalized_trade_date.replace('-', '')}.csv"

        artifacts: dict[str, str] = {}
        rows: list[dict[str, Any]] = []
        error_message: str | None = None

        try:
            fetch_result = respectful_get(session, self.url, self.logger, expect_euc_kr=True)
            html_text = decode_euc_kr_response(fetch_result.response)
            artifacts["raw_html"] = save_text(html_debug_path, html_text)

            try:
                rows = self.parse_with_pandas(html_text, normalized_trade_date, collected_at)
                self.logger.info("KBSEC market index parsed with pandas: %s rows", len(rows))
            except Exception as exc:
                self.logger.warning("pandas parsing failed for KBSEC market index: %s", exc)

            if not rows:
                rows = self.parse_with_text(html_text, normalized_trade_date, collected_at)
                artifacts["parsed_text"] = save_text(text_debug_path, "\n".join(extract_text_lines(html_text)))
                self.logger.info("KBSEC market index parsed with text fallback: %s rows", len(rows))

            validation = validate_market_index(rows)
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
                    "group_name",
                    "index_name",
                    "standard_index_name",
                    "current_value",
                    "change_value",
                    "change_rate",
                    "direction",
                    "unit",
                    "raw_note",
                    "source",
                    "source_url",
                    "collected_at",
                    "raw_hash",
                ],
            )
            return {
                "collector": "kbsec_market_index",
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
                    "group_name",
                    "index_name",
                    "standard_index_name",
                    "current_value",
                    "change_value",
                    "change_rate",
                    "direction",
                    "unit",
                    "raw_note",
                    "source",
                    "source_url",
                    "collected_at",
                    "raw_hash",
                ],
            )
            self.logger.error("KBSEC market index collection failed: %s", exc)
            return {
                "collector": "kbsec_market_index",
                "status": "failed",
                "row_count": 0,
                "validation": {"valid": False, "errors": [error_message], "row_count": 0},
                "files": artifacts,
                "requests_success": False,
                "playwright_used": "screenshot" in artifacts,
                "error_message": error_message,
                "source_url": self.url,
            }
