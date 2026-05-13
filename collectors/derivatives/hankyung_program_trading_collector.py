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
from .validators import validate_program_trading

URL = "https://markets.hankyung.com/investment/program-trading"
SOURCE = "HANKYUNG"
PROGRAM_TYPE_MAP = {
    "차익거래": "ARBITRAGE",
    "비차익거래": "NON_ARBITRAGE",
    "전체": "TOTAL",
}


class HankyungProgramTradingCollector:
    url = URL
    source = SOURCE

    def __init__(self, output_root: str | Path = ".", logger: logging.Logger | None = None) -> None:
        self.output_root = Path(output_root)
        self.logger = logger or logging.getLogger(__name__)

    @staticmethod
    def _extract_page_trade_date(html_text: str, fallback_trade_date: str) -> str:
        match = re.search(r"(\d{4}\.\d{2}\.\d{2})\s*장마감", html_text)
        if match:
            return normalize_trade_date(match.group(1))
        return fallback_trade_date

    @staticmethod
    def _extract_unit_value(columns: list[tuple[Any, Any]]) -> str | None:
        for group_name, _ in columns:
            text = normalize_whitespace(group_name)
            unit_match = re.search(r"\(([^)]+)\)", text)
            if unit_match:
                return unit_match.group(1)
        return None

    def parse_with_pandas(self, html_text: str, fallback_trade_date: str, collected_at: str) -> list[dict[str, Any]]:
        dataframes = pd.read_html(StringIO(html_text))
        if len(dataframes) < 2:
            return []
        dataframe = dataframes[1]
        page_trade_date = self._extract_page_trade_date(html_text, fallback_trade_date)
        current_year = int(page_trade_date[:4])
        rows: list[dict[str, Any]] = []
        unit_value = self._extract_unit_value(list(dataframe.columns))
        raw_hash = compute_raw_hash(html_text)
        date_column = dataframe.columns[0]
        column_map = {(normalize_whitespace(level0), normalize_whitespace(level1)): column for column in dataframe.columns for level0, level1 in [column]}

        for _, series in dataframe.iterrows():
            date_label = normalize_whitespace(series[date_column])
            normalized_date = normalize_trade_date(date_label, fallback=pd.Timestamp(page_trade_date).date())
            if not normalized_date.startswith(str(current_year)):
                normalized_date = f"{current_year}-{normalized_date[5:]}"

            for raw_program_name, program_type in PROGRAM_TYPE_MAP.items():
                buy_column = column_map[(f"{raw_program_name}(백만원)", "매수")]
                sell_column = column_map[(f"{raw_program_name}(백만원)", "매도")]
                net_column = column_map[(f"{raw_program_name}(백만원)", "순매수")]
                rows.append(
                    {
                        "trade_date": normalized_date,
                        "market": "KOSPI",
                        "program_type": program_type,
                        "sell_value": normalize_signed_number(series[sell_column]),
                        "buy_value": normalize_signed_number(series[buy_column]),
                        "net_buy_value": normalize_signed_number(series[net_column]),
                        "sell_volume": None,
                        "buy_volume": None,
                        "net_buy_volume": None,
                        "unit_value": unit_value,
                        "unit_volume": None,
                        "source": self.source,
                        "source_url": self.url,
                        "collected_at": collected_at,
                        "raw_hash": raw_hash,
                        **time_fields_for_row(
                            collected_at=collected_at,
                            base_time=None,
                            source_time="15:30" if normalized_date == page_trade_date else None,
                        ),
                    }
                )
        return rows

    def parse_with_text(self, html_text: str, fallback_trade_date: str, collected_at: str) -> list[dict[str, Any]]:
        lines = extract_text_lines(html_text)
        page_trade_date = self._extract_page_trade_date(html_text, fallback_trade_date)
        current_year = int(page_trade_date[:4])
        rows: list[dict[str, Any]] = []
        raw_hash = compute_raw_hash(html_text)

        header_token = "일자"
        if header_token not in lines:
            return []
        start = lines.index(header_token)
        data_start = start
        for idx in range(start, len(lines) - 1):
            if lines[idx] == "일자" and lines[idx + 1] == "매수":
                data_start = idx + 10
                break

        for idx in range(data_start, len(lines), 10):
            chunk = lines[idx : idx + 10]
            if len(chunk) < 10:
                break
            if not re.fullmatch(r"\d{2}\.\d{2}", chunk[0]):
                continue
            normalized_date = normalize_trade_date(chunk[0], fallback=pd.Timestamp(page_trade_date).date())
            if not normalized_date.startswith(str(current_year)):
                normalized_date = f"{current_year}-{normalized_date[5:]}"
            values = [normalize_signed_number(item) for item in chunk[1:10]]
            mappings = [
                ("ARBITRAGE", values[1], values[0], values[2]),
                ("NON_ARBITRAGE", values[4], values[3], values[5]),
                ("TOTAL", values[7], values[6], values[8]),
            ]
            for program_type, sell_value, buy_value, net_buy_value in mappings:
                rows.append(
                    {
                        "trade_date": normalized_date,
                        "market": "KOSPI",
                        "program_type": program_type,
                        "sell_value": sell_value,
                        "buy_value": buy_value,
                        "net_buy_value": net_buy_value,
                        "sell_volume": None,
                        "buy_volume": None,
                        "net_buy_volume": None,
                        "unit_value": "백만원",
                        "unit_volume": None,
                        "source": self.source,
                        "source_url": self.url,
                        "collected_at": collected_at,
                        "raw_hash": raw_hash,
                        **time_fields_for_row(
                            collected_at=collected_at,
                            base_time=None,
                            source_time="15:30" if normalized_date == page_trade_date else None,
                        ),
                    }
                )
        return rows

    def _playwright_fallback(self, debug_dir: Path) -> dict[str, str]:
        artifacts: dict[str, str] = {}
        try:
            from playwright.sync_api import sync_playwright

            screenshot_path = debug_dir / "screenshots" / "hankyung_program_trading.png"
            html_path = debug_dir / "hankyung_program_trading_playwright.html"
            text_path = debug_dir / "hankyung_program_trading_playwright.txt"
            network_path = debug_dir / "network" / "hankyung_program_trading_network.json"

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
            self.logger.warning("Playwright fallback failed for Hankyung program trading: %s", exc)
        return artifacts

    def collect(self, trade_date: str | None = None) -> dict[str, Any]:
        session = create_requests_session()
        collected_at = current_timestamp()
        normalized_trade_date = normalize_trade_date(trade_date)

        debug_dir = self.output_root / "debug"
        raw_dir = self.output_root / "data" / "raw"
        html_debug_path = debug_dir / "hankyung_program_trading_raw.html"
        text_debug_path = debug_dir / "hankyung_program_trading_parsed.txt"
        json_path = raw_dir / f"hankyung_program_trading_{normalized_trade_date.replace('-', '')}.json"
        csv_path = raw_dir / f"hankyung_program_trading_{normalized_trade_date.replace('-', '')}.csv"

        artifacts: dict[str, str] = {}
        rows: list[dict[str, Any]] = []
        error_message: str | None = None

        try:
            fetch_result = respectful_get(session, self.url, self.logger, expect_euc_kr=False)
            html_text = fetch_result.response.text
            artifacts["raw_html"] = save_text(html_debug_path, html_text)

            try:
                rows = self.parse_with_pandas(html_text, normalized_trade_date, collected_at)
                self.logger.info("Hankyung program trading parsed with pandas: %s rows", len(rows))
            except Exception as exc:
                self.logger.warning("pandas parsing failed for Hankyung program trading: %s", exc)

            if not rows:
                rows = self.parse_with_text(html_text, normalized_trade_date, collected_at)
                artifacts["parsed_text"] = save_text(text_debug_path, "\n".join(extract_text_lines(html_text)))
                self.logger.info("Hankyung program trading parsed with text fallback: %s rows", len(rows))

            validation = validate_program_trading(rows)
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
                    "market",
                    "program_type",
                    "sell_value",
                    "buy_value",
                    "net_buy_value",
                    "sell_volume",
                    "buy_volume",
                    "net_buy_volume",
                    "unit_value",
                    "unit_volume",
                    "source",
                    "source_url",
                    "collected_at",
                    "raw_hash",
                ],
            )
            return {
                "collector": "hankyung_program_trading",
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
                    "market",
                    "program_type",
                    "sell_value",
                    "buy_value",
                    "net_buy_value",
                    "sell_volume",
                    "buy_volume",
                    "net_buy_volume",
                    "unit_value",
                    "unit_volume",
                    "source",
                    "source_url",
                    "collected_at",
                    "raw_hash",
                ],
            )
            self.logger.error("Hankyung program trading collection failed: %s", exc)
            return {
                "collector": "hankyung_program_trading",
                "status": "failed",
                "row_count": 0,
                "validation": {"valid": False, "errors": [error_message], "row_count": 0},
                "files": artifacts,
                "requests_success": False,
                "playwright_used": "screenshot" in artifacts,
                "error_message": error_message,
                "source_url": self.url,
            }
