from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import requests
from supabase import create_client

from .common import current_timestamp, load_api_keys_config, save_json


class KISAuthProbe:
    def __init__(self, output_root: str | Path = ".") -> None:
        self.output_root = Path(output_root)

    def verify(self, api_keys_path: str | None = None) -> dict[str, Any]:
        config, resolved_path = load_api_keys_config(api_keys_path, self.output_root)
        collected_at = current_timestamp()

        if not resolved_path:
            result = {
                "status": "skipped",
                "source": "KIS",
                "collected_at": collected_at,
                "config_path": None,
                "error_message": "api_keys.json not found",
            }
            self._save(result)
            return result

        kis = config.get("kis", {})
        app_key = kis.get("app_key", "")
        app_secret = kis.get("app_secret", "")
        account_no = kis.get("account_no", "")
        product_code = kis.get("product_code", "")
        is_real = bool(kis.get("is_real", True))

        base_url = "https://openapi.koreainvestment.com:9443" if is_real else "https://openvts.koreainvestment.com:7070"
        supabase_cfg = config.get("supabase", {})

        result: dict[str, Any] = {
            "status": "failed",
            "source": "KIS",
            "collected_at": collected_at,
            "config_path": resolved_path,
            "base_url": base_url,
            "has_app_key": bool(app_key),
            "has_app_secret": bool(app_secret),
            "has_account_no": bool(account_no),
            "product_code_present": bool(product_code),
            "is_real": is_real,
        }

        if not app_key or not app_secret:
            result["error_message"] = "KIS app_key/app_secret missing"
            self._save(result)
            return result

        supabase_client = None
        if supabase_cfg.get("url") and supabase_cfg.get("service_role_key"):
            try:
                supabase_client = create_client(supabase_cfg["url"], supabase_cfg["service_role_key"])
                rows = supabase_client.table("api_tokens").select("token_value,expires_at").eq("service_name", "kis").limit(1).execute().data or []
                if rows and rows[0].get("token_value"):
                    result.update(
                        {
                            "status": "success",
                            "http_status": None,
                            "token_type": "Bearer",
                            "expires_in": None,
                            "expires_at": rows[0].get("expires_at"),
                            "token_received": True,
                            "error_message": None,
                            "token_source": "supabase_cache",
                        }
                    )
                    self._save(result)
                    return result
            except Exception as exc:
                result["supabase_cache_error"] = str(exc)

        response = requests.post(
            f"{base_url}/oauth2/tokenP",
            json={
                "grant_type": "client_credentials",
                "appkey": app_key,
                "appsecret": app_secret,
            },
            timeout=20,
        )
        result["http_status"] = response.status_code
        response.raise_for_status()
        payload = response.json()

        access_token = payload.get("access_token")
        expires_in = payload.get("expires_in")
        token_type = payload.get("token_type")
        expires_at = None
        if isinstance(expires_in, int):
            expires_at = (datetime.now(timezone.utc) + timedelta(seconds=expires_in)).isoformat()

        result.update(
            {
                "status": "success" if bool(access_token) else "failed",
                "token_type": token_type,
                "expires_in": expires_in,
                "expires_at": expires_at,
                "token_received": bool(access_token),
                "error_message": None if access_token else "access_token missing in response",
                "token_source": "fresh_issue",
            }
        )
        if supabase_client is not None and access_token and expires_at:
            try:
                supabase_client.table("api_tokens").upsert(
                    {
                        "service_name": "kis",
                        "token_value": access_token,
                        "expires_at": expires_at,
                    }
                ).execute()
            except Exception as exc:
                result["supabase_save_error"] = str(exc)
        self._save(result)
        return result

    def _save(self, payload: dict[str, Any]) -> str:
        trade_date = payload["collected_at"][:10].replace("-", "")
        debug_path = self.output_root / "debug" / "network" / f"kis_auth_status_{trade_date}.json"
        return save_json(debug_path, payload)
