from __future__ import annotations

import logging
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import requests
from supabase import create_client

from .common import (
    build_run_context,
    build_slot_suffix,
    compute_raw_hash,
    current_timestamp,
    enrich_row_with_run_context,
    hhmm_from_timestamp,
    load_api_keys_config,
    normalize_signed_number,
    normalize_trade_date,
    payload_with_status,
    save_csv,
    save_json,
    time_fields_for_row,
)

SOURCE = "KIS"
BOARD_URL_PATH = "/uapi/domestic-futureoption/v1/quotations/display-board-futures"
PRICE_URL_PATH = "/uapi/domestic-futureoption/v1/quotations/inquire-price"
DAILY_URL_PATH = "/uapi/domestic-futureoption/v1/quotations/inquire-daily-fuopchartprice"


def validate_kis_futures(rows: list[dict[str, Any]]) -> dict[str, Any]:
    errors: list[str] = []
    if not rows:
        errors.append("No KIS futures snapshot rows")
    else:
        row = rows[0]
        for field in ["current_price", "market_basis", "open_interest", "futures_code", "futures_name"]:
            if row.get(field) in {None, ""}:
                errors.append(f"{field} is missing")
    return {"valid": not errors, "errors": errors, "row_count": len(rows)}


class KISTokenProvider:
    def __init__(self, config: dict[str, Any], logger: logging.Logger | None = None) -> None:
        self.config = config
        self.logger = logger or logging.getLogger(__name__)
        self.kis = config.get("kis", {})
        self.supabase = config.get("supabase", {})
        self.base_url = "https://openapi.koreainvestment.com:9443" if self.kis.get("is_real", True) else "https://openvts.koreainvestment.com:7070"

    def _supabase_client(self):
        url = self.supabase.get("url")
        key = self.supabase.get("service_role_key")
        if not url or not key:
            return None
        return create_client(url, key)

    def get_token(self) -> tuple[str, str]:
        client = self._supabase_client()
        if client is not None:
            try:
                rows = client.table("api_tokens").select("token_value,expires_at").eq("service_name", "kis").limit(1).execute().data or []
                if rows and rows[0].get("token_value"):
                    self.logger.info("Loaded KIS token from Supabase cache.")
                    return rows[0]["token_value"], "supabase_cache"
            except Exception as exc:
                self.logger.warning("Failed to read KIS token from Supabase cache: %s", exc)

        payload = {
            "grant_type": "client_credentials",
            "appkey": self.kis.get("app_key", ""),
            "appsecret": self.kis.get("app_secret", ""),
        }
        response = requests.post(f"{self.base_url}/oauth2/tokenP", json=payload, timeout=20)
        response.raise_for_status()
        token_payload = response.json()
        token = token_payload["access_token"]
        expires_in = token_payload.get("expires_in", 23 * 3600)

        if client is not None:
            try:
                expires_at = (date.today()).isoformat()
                from datetime import datetime, timezone

                expires_at = (datetime.now(timezone.utc) + timedelta(seconds=int(expires_in))).isoformat()
                client.table("api_tokens").upsert(
                    {
                        "service_name": "kis",
                        "token_value": token,
                        "expires_at": expires_at,
                    }
                ).execute()
                self.logger.info("Saved fresh KIS token to Supabase cache.")
            except Exception as exc:
                self.logger.warning("Failed to persist KIS token to Supabase cache: %s", exc)

        return token, "fresh_issue"


class KISIndexFuturesCollector:
    source = SOURCE

    def __init__(self, output_root: str | Path = ".", logger: logging.Logger | None = None) -> None:
        self.output_root = Path(output_root)
        self.logger = logger or logging.getLogger(__name__)

    def _headers(self, token: str, tr_id: str, app_key: str, app_secret: str) -> dict[str, str]:
        return {
            "content-type": "application/json; charset=utf-8",
            "authorization": f"Bearer {token}",
            "appkey": app_key,
            "appsecret": app_secret,
            "tr_id": tr_id,
            "custtype": "P",
        }

    def collect(self, trade_date: str | None = None, target_slot: str = "0930", api_keys_path: str | None = None, collected_at: str | None = None) -> dict[str, Any]:
        normalized_trade_date = normalize_trade_date(trade_date)
        collected_at = collected_at or current_timestamp()
        run_context = build_run_context(trade_date=normalized_trade_date, target_slot=target_slot, collected_at=collected_at)
        raw_dir = self.output_root / "data" / "raw"
        debug_dir = self.output_root / "debug" / "network"
        file_suffix = build_slot_suffix(normalized_trade_date, target_slot)
        json_snapshot_path = raw_dir / f"kis_index_futures_snapshot_{file_suffix}.json"
        csv_snapshot_path = raw_dir / f"kis_index_futures_snapshot_{file_suffix}.csv"
        json_daily_path = raw_dir / f"kis_index_futures_daily_{file_suffix}.json"
        csv_daily_path = raw_dir / f"kis_index_futures_daily_{file_suffix}.csv"

        config, config_path = load_api_keys_config(api_keys_path, self.output_root)
        kis = config.get("kis", {})
        app_key = kis.get("app_key", "")
        app_secret = kis.get("app_secret", "")
        is_real = bool(kis.get("is_real", True))
        base_url = "https://openapi.koreainvestment.com:9443" if is_real else "https://openvts.koreainvestment.com:7070"

        artifacts: dict[str, str] = {}
        if not app_key or not app_secret:
            error_message = "KIS app_key/app_secret missing"
            payload = payload_with_status(
                trade_date=normalized_trade_date,
                collected_at=collected_at,
                source=self.source,
                source_url=f"{base_url}{PRICE_URL_PATH}",
                data=[],
                status="failed",
                run_context=run_context,
                error_message=error_message,
                validation={"valid": False, "errors": [error_message], "row_count": 0},
            )
            artifacts["json_snapshot"] = save_json(json_snapshot_path, payload)
            artifacts["csv_snapshot"] = save_csv(csv_snapshot_path, [], ["trade_date"])
            artifacts["json_daily"] = save_json(json_daily_path, payload_with_status(
                trade_date=normalized_trade_date,
                collected_at=collected_at,
                source=self.source,
                source_url=f"{base_url}{DAILY_URL_PATH}",
                data=[],
                status="failed",
                run_context=run_context,
                error_message=error_message,
                validation={"valid": False, "errors": [error_message], "row_count": 0},
            ))
            artifacts["csv_daily"] = save_csv(csv_daily_path, [], ["trade_date"])
            return {
                "collector": "kis_index_futures",
                "status": "failed",
                "row_count": 0,
                "validation": {"valid": False, "errors": [error_message], "row_count": 0},
                "files": artifacts,
                "requests_success": False,
                "playwright_used": False,
                "error_message": error_message,
                "source_url": f"{base_url}{PRICE_URL_PATH}",
            }

        token_provider = KISTokenProvider(config, logger=self.logger)
        token, token_source = token_provider.get_token()

        session = requests.Session()
        board_response = session.get(
            f"{base_url}{BOARD_URL_PATH}",
            headers=self._headers(token, "FHPIF05030200", app_key, app_secret),
            params={
                "FID_COND_MRKT_DIV_CODE": "F",
                "FID_COND_SCR_DIV_CODE": "20503",
                "FID_COND_MRKT_CLS_CODE": "",
            },
            timeout=20,
        )
        board_response.raise_for_status()
        board_payload = board_response.json()
        board_rows = board_payload.get("output", [])
        if not board_rows:
            raise RuntimeError(f"KIS display-board-futures returned no rows: {board_payload.get('msg1')}")

        front_contract = board_rows[0]
        futures_code = front_contract.get("futs_shrn_iscd")
        futures_name = front_contract.get("hts_kor_isnm")

        price_response = session.get(
            f"{base_url}{PRICE_URL_PATH}",
            headers=self._headers(token, "FHMIF10000000", app_key, app_secret),
            params={
                "FID_COND_MRKT_DIV_CODE": "F",
                "FID_INPUT_ISCD": futures_code,
            },
            timeout=20,
        )
        price_response.raise_for_status()
        price_payload = price_response.json()

        output1 = price_payload.get("output1", {}) or {}
        output2 = price_payload.get("output2", {}) or {}
        output3 = price_payload.get("output3", {}) or {}

        snapshot_row = {
            "trade_date": normalized_trade_date,
            "market_type": "KOSPI200_INDEX_FUTURES",
            "futures_code": futures_code,
            "futures_name": futures_name,
            "current_price": normalize_signed_number(output1.get("futs_prpr")),
            "open_price": normalize_signed_number(output1.get("futs_oprc")),
            "high_price": normalize_signed_number(output1.get("futs_hgpr")),
            "low_price": normalize_signed_number(output1.get("futs_lwpr")),
            "previous_close": normalize_signed_number(output1.get("futs_prdy_clpr")),
            "change_value": normalize_signed_number(output1.get("futs_prdy_vrss")),
            "change_rate": normalize_signed_number(output1.get("futs_prdy_ctrt")),
            "accumulated_volume": normalize_signed_number(output1.get("acml_vol")),
            "accumulated_trading_value": normalize_signed_number(output1.get("acml_tr_pbmn")),
            "open_interest": normalize_signed_number(output1.get("hts_otst_stpl_qty")),
            "open_interest_change": normalize_signed_number(output1.get("otst_stpl_qty_icdc")),
            "theoretical_price": normalize_signed_number(output1.get("hts_thpr")),
            "spot_reference_price": normalize_signed_number(output1.get("futs_sdpr")),
            "basis": normalize_signed_number(output1.get("basis")),
            "market_basis": normalize_signed_number(output1.get("mrkt_basis")),
            "remaining_days": normalize_signed_number(output1.get("hts_rmnn_dynu")),
            "kospi_index_value": normalize_signed_number(output2.get("bstp_nmix_prpr")),
            "kospi200_index_value": normalize_signed_number(output3.get("bstp_nmix_prpr")),
            "token_source": token_source,
            "source": self.source,
            "source_url": f"{base_url}{PRICE_URL_PATH}",
            "collected_at": collected_at,
            "raw_hash": compute_raw_hash(save_json.__globals__["json"].dumps(price_payload, ensure_ascii=False)),
            **time_fields_for_row(
                collected_at=collected_at,
                base_time=output1.get("stck_cntg_hour") or output1.get("oprc_hour") or output1.get("acml_hour"),
                source_time=output1.get("stck_cntg_hour") or output1.get("oprc_hour") or output1.get("acml_hour"),
            ),
        }
        snapshot_row = enrich_row_with_run_context(snapshot_row, run_context)

        start_date = (date.fromisoformat(normalized_trade_date) - timedelta(days=14)).strftime("%Y%m%d")
        end_date = date.fromisoformat(normalized_trade_date).strftime("%Y%m%d")
        daily_response = session.get(
            f"{base_url}{DAILY_URL_PATH}",
            headers=self._headers(token, "FHKIF03020100", app_key, app_secret),
            params={
                "FID_COND_MRKT_DIV_CODE": "F",
                "FID_INPUT_ISCD": futures_code,
                "FID_INPUT_DATE_1": start_date,
                "FID_INPUT_DATE_2": end_date,
                "FID_PERIOD_DIV_CODE": "D",
            },
            timeout=20,
        )
        daily_response.raise_for_status()
        daily_payload = daily_response.json()

        daily_rows = []
        raw_hash_daily = compute_raw_hash(save_json.__globals__["json"].dumps(daily_payload, ensure_ascii=False))
        for row in daily_payload.get("output2", []) or []:
            daily_rows.append(
                enrich_row_with_run_context({
                    "trade_date": normalize_trade_date(row.get("stck_bsop_date"), fallback=date.fromisoformat(normalized_trade_date)),
                    "base_time": hhmm_from_timestamp(collected_at),
                    "base_time_source": "collected_at_fallback",
                    "source_time": hhmm_from_timestamp(collected_at),
                    "market_session": snapshot_row["market_session"],
                    "futures_code": futures_code,
                    "futures_name": futures_name,
                    "open_price": normalize_signed_number(row.get("futs_oprc")),
                    "high_price": normalize_signed_number(row.get("futs_hgpr")),
                    "low_price": normalize_signed_number(row.get("futs_lwpr")),
                    "close_price": normalize_signed_number(row.get("futs_prpr")),
                    "accumulated_volume": normalize_signed_number(row.get("acml_vol")),
                    "accumulated_trading_value": normalize_signed_number(row.get("acml_tr_pbmn")),
                    "source": self.source,
                    "source_url": f"{base_url}{DAILY_URL_PATH}",
                    "collected_at": collected_at,
                    "raw_hash": raw_hash_daily,
                }, run_context)
            )

        validation = validate_kis_futures([snapshot_row])
        status = "success" if validation["valid"] else "failed"
        error_message = None if validation["valid"] else "; ".join(validation["errors"])

        artifacts["debug_board"] = save_json(debug_dir / f"kis_index_futures_board_{file_suffix}.json", board_payload)
        artifacts["debug_price"] = save_json(debug_dir / f"kis_index_futures_price_{file_suffix}.json", price_payload)
        artifacts["debug_daily"] = save_json(debug_dir / f"kis_index_futures_daily_{file_suffix}.json", daily_payload)
        artifacts["json_snapshot"] = save_json(
            json_snapshot_path,
            payload_with_status(
                trade_date=normalized_trade_date,
                collected_at=collected_at,
                source=self.source,
                source_url=f"{base_url}{PRICE_URL_PATH}",
                data=[snapshot_row],
                status=status,
                run_context=run_context,
                error_message=error_message,
                validation=validation,
            ),
        )
        artifacts["csv_snapshot"] = save_csv(
            csv_snapshot_path,
            [snapshot_row],
            list(snapshot_row.keys()),
        )
        artifacts["json_daily"] = save_json(
            json_daily_path,
            payload_with_status(
                trade_date=normalized_trade_date,
                collected_at=collected_at,
                source=self.source,
                source_url=f"{base_url}{DAILY_URL_PATH}",
                data=daily_rows,
                status="success" if daily_rows else "failed",
                run_context=run_context,
                error_message=None if daily_rows else "No KIS futures daily rows",
                validation={"valid": bool(daily_rows), "errors": [] if daily_rows else ["No KIS futures daily rows"], "row_count": len(daily_rows)},
            ),
        )
        artifacts["csv_daily"] = save_csv(csv_daily_path, daily_rows, list(daily_rows[0].keys()) if daily_rows else ["trade_date"])

        return {
            "collector": "kis_index_futures",
            "status": status,
            "row_count": 1 + len(daily_rows),
            "validation": validation,
            "files": artifacts,
            "requests_success": True,
            "playwright_used": False,
            "error_message": error_message,
            "source_url": f"{base_url}{PRICE_URL_PATH}",
        }
