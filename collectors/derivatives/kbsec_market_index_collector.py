from __future__ import annotations

import logging
import re
from io import StringIO
from pathlib import Path
from typing import Any

import pandas as pd
from bs4 import BeautifulSoup

from .common import (
    PLAYWRIGHT_USER_AGENT,
    PLAYWRIGHT_VIEWPORT,
    build_run_context,
    build_slot_suffix,
    compute_raw_hash,
    create_requests_session,
    current_timestamp,
    decode_euc_kr_response,
    enrich_row_with_run_context,
    extract_text_lines,
    normalize_trade_date,
    normalize_whitespace,
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

SECTION_ID_TO_GROUP = {
    "stockKr": "DOMESTIC_INDEX",
    "stockEng": "GLOBAL_INDEX",
    "stockEtc": "FX_COMMODITY",
}

DATA_CODE_MAP = {
    "KGG01P": "KOSPI",
    "QGG01P": "KOSDAQ",
    "K2G01P": "KOSPI200",
    "Q5G01P": "KOSDAQ150",
    "A0166000": "KOSPI_FUTURES",
    "NAS@IXIC": "NASDAQ",
    "SPI@SPX": "SP500",
    "USDKRWSMBS": "USDKRW",
}

NAME_HINT_MAP = {
    "KOSPI200": "KOSPI200",
    "KOSPI 200": "KOSPI200",
    "200": "KOSPI200",
    "KOSPI": "KOSPI",
    "KOSDAQ150": "KOSDAQ150",
    "KOSDAQ 150": "KOSDAQ150",
    "KOSDAQ": "KOSDAQ",
    "NASDAQ": "NASDAQ",
    "S&P500": "SP500",
    "S&P 500": "SP500",
    "SP500": "SP500",
    "USDKRW": "USDKRW",
}


def _safe_number(value: Any) -> int | float | None:
    text = normalize_whitespace(value)
    if not text or text in {"-", "--", "N/A", "nan", "None"}:
        return None
    if re.fullmatch(r"\d{4}-\d{1,2}", text):
        return None
    sign = -1 if any(token in text for token in ["▼", "▽", "하락"]) or text.startswith("-") else 1
    cleaned = text.replace(",", "").replace("%", "")
    cleaned = re.sub(r"[▲△▽▼()]", " ", cleaned)
    cleaned = re.sub(r"[^0-9.\-]", "", cleaned)
    if cleaned.count(".") > 1:
        parts = cleaned.split(".")
        cleaned = "".join(parts[:-1]) + "." + parts[-1]
    cleaned = cleaned.strip()
    if cleaned in {"", "-", ".", "-."}:
        return None
    try:
        number = float(cleaned)
    except ValueError:
        return None
    number = abs(number) * sign
    if number.is_integer():
        return int(number)
    return number


def _safe_change_pair(value: Any) -> tuple[int | float | None, int | float | None, str | None]:
    text = normalize_whitespace(value)
    if not text:
        return None, None, None
    direction = None
    if any(token in text for token in ["▲", "△", "상승"]):
        direction = "UP"
    elif any(token in text for token in ["▼", "▽", "하락"]):
        direction = "DOWN"
    rate_match = re.search(r"\(([^)]*)%\)", text)
    rate = _safe_number(rate_match.group(1)) if rate_match else None
    change_text = re.sub(r"\([^)]*%\)", "", text)
    change_value = _safe_number(change_text)
    if direction == "DOWN":
        if change_value is not None:
            change_value = -abs(change_value)
        if rate is not None:
            rate = -abs(rate)
    elif direction == "UP":
        if change_value is not None:
            change_value = abs(change_value)
        if rate is not None:
            rate = abs(rate)
    elif change_value == 0:
        direction = "FLAT"
        if rate is None:
            rate = 0
    return change_value, rate, direction


class KBSECMarketIndexCollector:
    url = URL
    source = SOURCE

    def __init__(self, output_root: str | Path = ".", logger: logging.Logger | None = None) -> None:
        self.output_root = Path(output_root)
        self.logger = logger or logging.getLogger(__name__)

    @staticmethod
    def extract_raw_note(html_text: str) -> str | None:
        match = re.search(r"15\s*~\s*20\S+", html_text)
        return match.group(0) if match else None

    @staticmethod
    def standardize_index_name(raw_name: str, source_code: str | None = None) -> str:
        if source_code and source_code in DATA_CODE_MAP:
            return DATA_CODE_MAP[source_code]
        compact = re.sub(r"[^A-Za-z0-9]", "", normalize_whitespace(raw_name)).upper()
        for hint, standard_name in NAME_HINT_MAP.items():
            if re.sub(r"[^A-Za-z0-9]", "", hint).upper() in compact:
                return standard_name
        return normalize_whitespace(raw_name)

    @staticmethod
    def _is_invalid_label(text: str) -> bool:
        compact = normalize_whitespace(text)
        if not compact:
            return True
        if compact.startswith("15 ~ 20"):
            return True
        if re.fullmatch(r"\d{4}-\d{1,2}", compact):
            return True
        if re.fullmatch(r"[0-9.,()%+\- ]+", compact):
            return True
        return False

    def _build_row(
        self,
        *,
        trade_date: str,
        collected_at: str,
        group_name: str,
        source_code: str | None,
        raw_name: str,
        current_value_text: str,
        change_text: str,
        raw_hash: str,
        raw_note: str | None,
    ) -> dict[str, Any] | None:
        label = normalize_whitespace(raw_name)
        current_value = _safe_number(current_value_text)
        change_value, change_rate, direction = _safe_change_pair(change_text)
        if self._is_invalid_label(label):
            self.logger.warning("KBSEC market index skipped row due to invalid label: %r", label)
            return None
        if current_value is None:
            self.logger.warning(
                "KBSEC market index skipped row due to invalid current_value: label=%r value=%r",
                label,
                current_value_text,
            )
            return None
        return {
            "trade_date": trade_date,
            "group_name": group_name,
            "source_code": source_code,
            "index_name": label,
            "standard_index_name": self.standardize_index_name(label, source_code),
            "current_value": current_value,
            "change_value": change_value,
            "change_rate": change_rate,
            "direction": direction,
            "raw_current_value_text": current_value_text,
            "raw_change_text": change_text,
            "raw_data": {
                "source_code": source_code,
                "index_name": label,
                "current_value_text": current_value_text,
                "change_text": change_text,
                "current_value": current_value,
                "change_value": change_value,
                "change_rate": change_rate,
                "direction": direction,
            },
            "source_fields": {
                "label_field": "th",
                "current_value_field": "td[0]",
                "change_block_field": "td[1]",
                "data_code": source_code,
                "detail_group": "FUT" if source_code == "A0166000" else None,
                "realtime_feed_hint": "KBRSFFC0" if source_code == "A0166000" else None,
            },
            "volume": None,
            "trading_value": None,
            "unit": None,
            "raw_note": raw_note,
            "source": self.source,
            "source_url": self.url,
            "collected_at": collected_at,
            "raw_hash": raw_hash,
            **time_fields_for_row(collected_at=collected_at),
        }

    def parse_with_bs4(self, html_text: str, trade_date: str, collected_at: str) -> tuple[list[dict[str, Any]], int]:
        soup = BeautifulSoup(html_text, "html.parser")
        raw_hash = compute_raw_hash(html_text)
        raw_note = self.extract_raw_note(html_text)
        rows: list[dict[str, Any]] = []
        skipped_rows = 0

        for tbody_id, group_name in SECTION_ID_TO_GROUP.items():
            tbody = soup.find("tbody", id=tbody_id)
            if tbody is None:
                self.logger.warning("KBSEC market index missing tbody id=%s", tbody_id)
                continue
            for tr in tbody.find_all("tr"):
                source_code = tr.get("data-code")
                th = tr.find("th")
                tds = tr.find_all("td")
                row = self._build_row(
                    trade_date=trade_date,
                    collected_at=collected_at,
                    group_name=group_name,
                    source_code=source_code,
                    raw_name=th.get_text(" ", strip=True) if th else "",
                    current_value_text=tds[0].get_text(" ", strip=True) if len(tds) > 0 else "",
                    change_text=tds[1].get_text(" ", strip=True) if len(tds) > 1 else "",
                    raw_hash=raw_hash,
                    raw_note=raw_note,
                )
                if row is None:
                    skipped_rows += 1
                    continue
                rows.append(row)
        return rows, skipped_rows

    def parse_with_pandas(self, html_text: str, trade_date: str, collected_at: str) -> tuple[list[dict[str, Any]], int]:
        raw_hash = compute_raw_hash(html_text)
        raw_note = self.extract_raw_note(html_text)
        rows: list[dict[str, Any]] = []
        skipped_rows = 0
        for group_name, dataframe in zip(["DOMESTIC_INDEX", "GLOBAL_INDEX", "FX_COMMODITY"], pd.read_html(StringIO(html_text))):
            for _, series in dataframe.iterrows():
                raw_name = normalize_whitespace(series.iloc[0] if len(series) > 0 else "")
                current_value_text = normalize_whitespace(series.iloc[1] if len(series) > 1 else "")
                trailing = [normalize_whitespace(item) for item in series.iloc[2:] if normalize_whitespace(item)]
                change_text = " ".join(trailing[:2])
                row = self._build_row(
                    trade_date=trade_date,
                    collected_at=collected_at,
                    group_name=group_name,
                    source_code=None,
                    raw_name=raw_name,
                    current_value_text=current_value_text,
                    change_text=change_text,
                    raw_hash=raw_hash,
                    raw_note=raw_note,
                )
                if row is None:
                    skipped_rows += 1
                    continue
                rows.append(row)
        return rows, skipped_rows

    def parse_with_text(self, html_text: str, trade_date: str, collected_at: str) -> tuple[list[dict[str, Any]], int]:
        lines = extract_text_lines(html_text)
        raw_hash = compute_raw_hash(html_text)
        raw_note = self.extract_raw_note(html_text)
        rows: list[dict[str, Any]] = []
        skipped_rows = 0
        current_group = "DOMESTIC_INDEX"
        for index in range(len(lines) - 2):
            token = lines[index]
            if "해외" in token:
                current_group = "GLOBAL_INDEX"
                continue
            if "환율" in token or "유가" in token:
                current_group = "FX_COMMODITY"
                continue
            if self._is_invalid_label(token):
                continue
            current_value_text = lines[index + 1]
            change_text = lines[index + 2]
            if index + 3 < len(lines) and lines[index + 3].startswith("("):
                change_text = f"{change_text} {lines[index + 3]}"
            row = self._build_row(
                trade_date=trade_date,
                collected_at=collected_at,
                group_name=current_group,
                source_code=None,
                raw_name=token,
                current_value_text=current_value_text,
                change_text=change_text,
                raw_hash=raw_hash,
                raw_note=raw_note,
            )
            if row is None:
                skipped_rows += 1
                continue
            if any(existing["index_name"] == row["index_name"] and existing["group_name"] == row["group_name"] for existing in rows):
                continue
            rows.append(row)
        return rows, skipped_rows

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

    def collect(self, trade_date: str | None = None, target_slot: str = "0930", collected_at: str | None = None) -> dict[str, Any]:
        session = create_requests_session()
        collected_at = collected_at or current_timestamp()
        normalized_trade_date = normalize_trade_date(trade_date)
        run_context = build_run_context(trade_date=normalized_trade_date, target_slot=target_slot, collected_at=collected_at)
        file_suffix = build_slot_suffix(normalized_trade_date, target_slot)

        debug_dir = self.output_root / "debug"
        raw_dir = self.output_root / "data" / "raw"
        html_debug_path = debug_dir / "kbsec_market_index_raw.html"
        text_debug_path = debug_dir / "kbsec_market_index_parsed.txt"
        json_path = raw_dir / f"kbsec_market_index_{file_suffix}.json"
        csv_path = raw_dir / f"kbsec_market_index_{file_suffix}.csv"

        artifacts: dict[str, str] = {}
        rows: list[dict[str, Any]] = []
        skipped_rows = 0
        error_message: str | None = None

        try:
            fetch_result = respectful_get(session, self.url, self.logger, expect_euc_kr=True)
            html_text = decode_euc_kr_response(fetch_result.response)
            artifacts["raw_html"] = save_text(html_debug_path, html_text)

            try:
                rows, skipped_rows = self.parse_with_bs4(html_text, normalized_trade_date, collected_at)
                self.logger.info("KBSEC market index parsed with bs4: rows=%s skipped_rows=%s", len(rows), skipped_rows)
            except Exception as exc:
                self.logger.warning("bs4 parsing failed for KBSEC market index: %s", exc)

            if not rows:
                try:
                    rows, skipped_rows = self.parse_with_pandas(html_text, normalized_trade_date, collected_at)
                    self.logger.info("KBSEC market index parsed with pandas: rows=%s skipped_rows=%s", len(rows), skipped_rows)
                except Exception as exc:
                    self.logger.warning("pandas parsing failed for KBSEC market index: %s", exc)

            if not rows:
                rows, skipped_rows = self.parse_with_text(html_text, normalized_trade_date, collected_at)
                artifacts["parsed_text"] = save_text(text_debug_path, "\n".join(extract_text_lines(html_text)))
                self.logger.info("KBSEC market index parsed with text fallback: rows=%s skipped_rows=%s", len(rows), skipped_rows)

            rows = [enrich_row_with_run_context(row, run_context) for row in rows]
            validation = validate_market_index(rows)
            status = "success" if rows else "failed"
            if status == "failed":
                error_message = "; ".join(validation["errors"]) if validation["errors"] else "No valid KBSEC market index rows"
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
                run_context=run_context,
                error_message=error_message,
                validation={**validation, "skipped_rows": skipped_rows},
            )
            artifacts["json"] = save_json(json_path, payload)
            artifacts["csv"] = save_csv(
                csv_path,
                rows,
                [
                    "trade_date",
                    "target_slot",
                    "generated_at",
                    "actual_kst_time",
                    "schedule_lag_minutes",
                    "base_time",
                    "base_time_source",
                    "source_time",
                    "market_session",
                    "group_name",
                    "source_code",
                    "index_name",
                    "standard_index_name",
                    "current_value",
                    "change_value",
                    "change_rate",
                    "direction",
                    "raw_current_value_text",
                    "raw_change_text",
                    "raw_data",
                    "source_fields",
                    "volume",
                    "trading_value",
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
                "skipped_rows": skipped_rows,
                "validation": {**validation, "skipped_rows": skipped_rows},
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
                run_context=run_context,
                error_message=error_message,
                validation={"valid": False, "errors": [error_message], "row_count": 0, "skipped_rows": skipped_rows},
            )
            artifacts["json"] = save_json(json_path, payload)
            artifacts["csv"] = save_csv(
                csv_path,
                [],
                [
                    "trade_date",
                    "target_slot",
                    "generated_at",
                    "actual_kst_time",
                    "schedule_lag_minutes",
                    "base_time",
                    "base_time_source",
                    "source_time",
                    "market_session",
                    "group_name",
                    "source_code",
                    "index_name",
                    "standard_index_name",
                    "current_value",
                    "change_value",
                    "change_rate",
                    "direction",
                    "raw_current_value_text",
                    "raw_change_text",
                    "raw_data",
                    "source_fields",
                    "volume",
                    "trading_value",
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
                "skipped_rows": skipped_rows,
                "validation": {"valid": False, "errors": [error_message], "row_count": 0, "skipped_rows": skipped_rows},
                "files": artifacts,
                "requests_success": False,
                "playwright_used": "screenshot" in artifacts,
                "error_message": error_message,
                "source_url": self.url,
            }
