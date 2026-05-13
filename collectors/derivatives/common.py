from __future__ import annotations

import csv
import hashlib
import json
import logging
import random
import re
import time
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import requests

DEFAULT_MOBILE_USER_AGENT = (
    "Mozilla/5.0 (Linux; Android 13; Pixel 7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Mobile Safari/537.36"
)

DEFAULT_HEADERS = {
    "User-Agent": DEFAULT_MOBILE_USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
}

PLAYWRIGHT_VIEWPORT = {"width": 412, "height": 915}
PLAYWRIGHT_USER_AGENT = DEFAULT_MOBILE_USER_AGENT

REQUEST_TIMEOUT_SECONDS = 20
MIN_DELAY_SECONDS = 2.0
MAX_DELAY_SECONDS = 5.0
MAX_RETRIES = 2

_LAST_REQUEST_BY_DOMAIN: dict[str, float] = {}
_ROBOTS_CACHE: dict[tuple[str, str], bool | None] = {}


@dataclass
class FetchResult:
    response: requests.Response
    attempts: int
    robots_allowed: bool | None


def ensure_directory(path: str | Path) -> Path:
    target = Path(path)
    target.mkdir(parents=True, exist_ok=True)
    return target


def create_requests_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(DEFAULT_HEADERS)
    return session


def setup_logger(log_path: str | Path, logger_name: str = "derivatives_data_collector") -> logging.Logger:
    ensure_directory(Path(log_path).parent)
    logger = logging.getLogger(logger_name)
    logger.setLevel(logging.INFO)
    logger.handlers.clear()

    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")

    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)

    logger.propagate = False
    return logger


def respect_rate_limit(url: str, logger: logging.Logger | None = None) -> None:
    domain = urlparse(url).netloc
    now = time.time()
    previous = _LAST_REQUEST_BY_DOMAIN.get(domain)
    if previous is not None:
        minimum_wait = random.uniform(MIN_DELAY_SECONDS, MAX_DELAY_SECONDS)
        elapsed = now - previous
        if elapsed < minimum_wait:
            wait_time = minimum_wait - elapsed
            if logger:
                logger.info("Waiting %.2f seconds before requesting %s", wait_time, domain)
            time.sleep(wait_time)
    _LAST_REQUEST_BY_DOMAIN[domain] = time.time()


def check_robots_allowed(url: str, user_agent: str = DEFAULT_MOBILE_USER_AGENT, logger: logging.Logger | None = None) -> bool | None:
    parsed = urlparse(url)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    cache_key = (robots_url, user_agent)
    if cache_key in _ROBOTS_CACHE:
        allowed = _ROBOTS_CACHE[cache_key]
        if logger:
            logger.info("robots.txt cache hit for %s: allowed=%s", url, allowed)
        return allowed
    try:
        response = requests.get(robots_url, headers={"User-Agent": user_agent}, timeout=REQUEST_TIMEOUT_SECONDS)
        response.raise_for_status()
        encoding = response.encoding or response.apparent_encoding or "utf-8"
        robots_text = response.content.decode(encoding, errors="ignore")
        parser = RobotFileParser()
        parser.parse(robots_text.splitlines())
        allowed = parser.can_fetch(user_agent, url)
        _ROBOTS_CACHE[cache_key] = allowed
        if logger:
            logger.info("robots.txt checked for %s: allowed=%s via %s", url, allowed, robots_url)
            logger.info("Terms of service were not auto-parsed; manual review is still recommended.")
        return allowed
    except Exception as exc:
        _ROBOTS_CACHE[cache_key] = None
        if logger:
            logger.warning("robots.txt check failed for %s: %s", robots_url, exc)
        return None


def respectful_get(
    session: requests.Session,
    url: str,
    logger: logging.Logger,
    *,
    max_retries: int = MAX_RETRIES,
    timeout: int = REQUEST_TIMEOUT_SECONDS,
    expect_euc_kr: bool = False,
) -> FetchResult:
    robots_allowed = check_robots_allowed(url, logger=logger)
    if robots_allowed is False:
        raise RuntimeError(f"robots.txt disallows fetching {url}")

    last_error: Exception | None = None
    for attempt in range(1, max_retries + 2):
        try:
            respect_rate_limit(url, logger=logger)
            response = session.get(url, timeout=timeout)
            if expect_euc_kr:
                response.encoding = "euc-kr"
            logger.info("GET %s -> %s (attempt %s)", url, response.status_code, attempt)
            response.raise_for_status()
            return FetchResult(response=response, attempts=attempt, robots_allowed=robots_allowed)
        except Exception as exc:
            last_error = exc
            logger.warning("Request failed for %s on attempt %s: %s", url, attempt, exc)
            if attempt > max_retries:
                break
    raise RuntimeError(f"Request failed for {url}: {last_error}") from last_error


def decode_euc_kr_response(response: requests.Response) -> str:
    response.encoding = "euc-kr"
    return response.text


def normalize_whitespace(value: Any) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def normalize_signed_number(value: Any) -> int | float | None:
    if value is None:
        return None

    text = normalize_whitespace(value)
    if text in {"", "-", "N/A", "nan", "None"}:
        return None

    sign = -1 if text.startswith("-") or "▼" in text else 1
    cleaned = text.replace(",", "")
    cleaned = re.sub(r"[+▲▼()％%억원백만원주]", " ", cleaned)
    cleaned = re.sub(r"[^0-9.\-]", " ", cleaned)
    cleaned = normalize_whitespace(cleaned).replace(" ", "")
    if cleaned in {"", "-", ".", "-."}:
        return None

    cleaned = cleaned.lstrip("+")
    cleaned = cleaned.replace("--", "-")
    if cleaned in {"-0", "-0.0", "0", "0.0"}:
        return 0

    number = float(cleaned)
    number = abs(number) * sign
    if number.is_integer():
        return int(number)
    return number


def normalize_change_direction(value: Any) -> str | None:
    text = str(value or "")
    if "▲" in text:
        return "UP"
    if "▼" in text:
        return "DOWN"
    if normalize_signed_number(value) == 0:
        return "FLAT"
    return None


def parse_change_pair(value: Any) -> tuple[int | float | None, int | float | None, str | None]:
    text = normalize_whitespace(value)
    if not text:
        return None, None, None
    direction = normalize_change_direction(text)
    rate_match = re.search(r"\(([-+0-9.,]+)%\)", text)
    rate = None
    if rate_match:
        rate = normalize_signed_number(rate_match.group(1))
        if direction == "DOWN" and rate is not None:
            rate = -abs(rate)
    change_text = re.sub(r"\([^)]+\)", "", text).strip()
    change_value = normalize_signed_number(change_text)
    if direction == "DOWN" and change_value is not None:
        change_value = -abs(change_value)
    elif direction == "UP" and change_value is not None:
        change_value = abs(change_value)
    return change_value, rate, direction


def normalize_trade_date(value: str | None = None, *, fallback: date | None = None) -> str:
    if value:
        text = value.strip()
        for fmt in ("%Y-%m-%d", "%Y.%m.%d", "%Y/%m/%d", "%Y%m%d"):
            try:
                parsed = datetime.strptime(text, fmt)
                return parsed.date().isoformat()
            except ValueError:
                continue
        month_day_match = re.fullmatch(r"(\d{1,2})[.-](\d{1,2})", text)
        if month_day_match:
            year = (fallback or date.today()).year
            month = int(month_day_match.group(1))
            day = int(month_day_match.group(2))
            return date(year, month, day).isoformat()
    return (fallback or date.today()).isoformat()


def current_timestamp() -> str:
    return datetime.now().astimezone().isoformat()


def compute_raw_hash(raw_text: str) -> str:
    return hashlib.sha256(raw_text.encode("utf-8", errors="ignore")).hexdigest()


def save_text(path: str | Path, text: str) -> str:
    target = Path(path)
    ensure_directory(target.parent)
    target.write_text(text, encoding="utf-8")
    return str(target)


def save_json(path: str | Path, payload: dict[str, Any]) -> str:
    target = Path(path)
    ensure_directory(target.parent)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(target)


def load_json(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def save_csv(path: str | Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> str:
    target = Path(path)
    ensure_directory(target.parent)
    with target.open("w", encoding="utf-8-sig", newline="") as file_obj:
        writer = csv.DictWriter(file_obj, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key) for key in fieldnames})
    return str(target)


def payload_with_status(
    *,
    trade_date: str,
    collected_at: str,
    source: str,
    source_url: str,
    data: list[dict[str, Any]],
    status: str,
    error_message: str | None = None,
    validation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "trade_date": trade_date,
        "collected_at": collected_at,
        "source": source,
        "source_url": source_url,
        "status": status,
        "data": data,
    }
    if error_message:
        payload["error_message"] = error_message
    if validation is not None:
        payload["validation"] = validation
    return payload


def extract_text_lines(html_text: str) -> list[str]:
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html_text, "html.parser")
    return [normalize_whitespace(line) for line in soup.get_text("\n", strip=True).splitlines() if normalize_whitespace(line)]


def load_api_keys_config(explicit_path: str | Path | None = None, search_root: str | Path = ".") -> tuple[dict[str, Any], str | None]:
    candidates: list[Path] = []
    if explicit_path:
        candidates.append(Path(explicit_path))

    root = Path(search_root)
    candidates.extend(
        [
            root / "config" / "api_keys.json",
            root / "api_keys.json",
            Path(r"E:\develop\StockData\config\api_keys.json"),
        ]
    )

    for candidate in candidates:
        if candidate.exists():
            return json.loads(candidate.read_text(encoding="utf-8")), str(candidate)
    return {}, None
