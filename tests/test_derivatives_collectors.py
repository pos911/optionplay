from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from collectors.derivatives.hankyung_program_trading_collector import HankyungProgramTradingCollector
from collectors.derivatives.kis_index_futures_collector import validate_kis_futures
from collectors.derivatives.kbsec_investor_trend_collector import KBSECInvestorTrendCollector
from collectors.derivatives.kbsec_market_index_collector import KBSECMarketIndexCollector
from collectors.derivatives.common import normalize_signed_number, save_json
from collectors.derivatives.report_builder import build_derivatives_data_report
from collectors.derivatives.validators import (
    validate_investor_flow,
    validate_market_index,
    validate_program_trading,
)

SAMPLE_KB_INVESTOR_HTML = """
<html><body>
<table>
  <tr><th>구분</th><th>외국인</th><th>개인</th><th>기관계</th></tr>
  <tr><td>코스피</td><td>-37,586</td><td>18,868</td><td>16,876</td></tr>
  <tr><td>코스피200 선물</td><td>-5,350</td><td>696</td><td>4,767</td></tr>
  <tr><td>코스피200 콜옵션</td><td>-8</td><td>9</td><td>-0</td></tr>
  <tr><td>코스피200 풋옵션</td><td>4</td><td>-3</td><td>-1</td></tr>
</table>
</body></html>
"""

SAMPLE_KB_INDEX_HTML = """
<html><body>
<table>
  <tr><td>코스피 종합</td><td>2,700.10</td><td>▲ 25.30 (0.95%)</td></tr>
  <tr><td>코스피 200</td><td>355.44</td><td>▼ 1.11 (0.31%)</td></tr>
  <tr><td>KOSPI선물</td><td>354.80</td><td>▲ 0.20 (0.06%)</td></tr>
</table>
<table>
  <tr><td>나스닥 종합</td><td>18,001.20</td><td>▲ 100.00 (0.56%)</td></tr>
</table>
<table>
  <tr><td>원/달러</td><td>1,360.50</td><td>▼ 2.10 (0.15%)</td></tr>
</table>
15 ~ 20분 지연 또는 종가지수입니다.
</body></html>
"""

SAMPLE_KB_INDEX_HTML_WITH_NOISE = """
<html><body>
<table>
  <tr><td>공지</td><td>2026-6</td><td>0.000.00</td></tr>
</table>
<table>
  <tr><td>코스피 200</td><td>355.44</td><td>▼ 1.11 (0.31%)</td></tr>
  <tr><td>KOSPI선물</td><td>354.80</td><td>▲ 0.20 (0.06%)</td></tr>
  <tr><td>잘못된 행</td><td>2026-6</td><td>0.000.00</td></tr>
</table>
<table>
  <tr><td>원/달러</td><td>1,360.50</td><td>▼ 2.10 (0.15%)</td></tr>
</table>
15 ~ 20분 지연 또는 종가지수입니다.
</body></html>
"""

SAMPLE_HANKYUNG_HTML = """
<html><body>
단위 : 백만원, 2026.05.13 장마감
<table><tr><th>05.13</th></tr><tr><td>5.12</td></tr></table>
<table>
  <thead>
    <tr>
      <th rowspan="2">일자</th>
      <th colspan="3">차익거래(백만원)</th>
      <th colspan="3">비차익거래(백만원)</th>
      <th colspan="3">전체(백만원)</th>
    </tr>
    <tr>
      <th>매수</th><th>매도</th><th>순매수</th>
      <th>매수</th><th>매도</th><th>순매수</th>
      <th>매수</th><th>매도</th><th>순매수</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td>5.13</td>
      <td>566,542</td><td>548,547</td><td>17,996</td>
      <td>13,268,795</td><td>14,801,503</td><td>-1,532,707</td>
      <td>13,835,338</td><td>15,350,049</td><td>-1,514,712</td>
    </tr>
  </tbody>
</table>
</body></html>
"""


class TestCommonHelpers(unittest.TestCase):
    def test_normalize_signed_number(self) -> None:
        self.assertEqual(normalize_signed_number("-0"), 0)
        self.assertEqual(normalize_signed_number("▲ 200.86"), 200.86)
        self.assertEqual(normalize_signed_number("▼ 2.36"), -2.36)
        self.assertIsNone(normalize_signed_number("N/A"))
        self.assertEqual(normalize_signed_number("0.000.00"), 0)
        self.assertIsNone(normalize_signed_number("2026-6"))


class TestCollectors(unittest.TestCase):
    def test_category_mapping(self) -> None:
        self.assertEqual(KBSECInvestorTrendCollector.map_category("코스피200 선물"), "KOSPI200_FUTURES")
        self.assertEqual(KBSECInvestorTrendCollector.map_category("미니 풋옵션"), "MINI_PUT_OPTIONS")

    def test_parse_kb_investor_html(self) -> None:
        collector = KBSECInvestorTrendCollector()
        rows = collector.parse_with_pandas(SAMPLE_KB_INVESTOR_HTML, "2026-05-13", "2026-05-13T10:00:00+09:00")
        validation = validate_investor_flow(rows)
        self.assertTrue(validation["valid"])
        target = {row["category"]: row for row in rows}
        self.assertEqual(target["KOSPI200_FUTURES"]["foreigner_net_buy"], -5350)
        self.assertEqual(target["KOSPI200_CALL_OPTIONS"]["institution_net_buy"], 0)
        self.assertEqual(target["KOSPI200_FUTURES"]["base_time"], "10:00")
        self.assertEqual(target["KOSPI200_FUTURES"]["base_time_source"], "collected_at_fallback")
        self.assertEqual(target["KOSPI200_FUTURES"]["market_session"], "REGULAR")

    def test_parse_kb_market_index_html(self) -> None:
        collector = KBSECMarketIndexCollector()
        rows = collector.parse_with_pandas(SAMPLE_KB_INDEX_HTML, "2026-05-13", "2026-05-13T10:00:00+09:00")
        validation = validate_market_index(rows)
        self.assertTrue(validation["valid"])
        target = {row["standard_index_name"]: row for row in rows}
        self.assertEqual(target["KOSPI200"]["direction"], "DOWN")
        self.assertEqual(target["USDKRW"]["current_value"], 1360.5)
        self.assertEqual(target["KOSPI200"]["base_time"], "10:00")

    def test_parse_kb_market_index_html_with_noise(self) -> None:
        collector = KBSECMarketIndexCollector()
        rows = collector.parse_with_pandas(SAMPLE_KB_INDEX_HTML_WITH_NOISE, "2026-05-13", "2026-05-13T10:00:00+09:00")
        validation = validate_market_index(rows)
        self.assertTrue(validation["valid"])
        target = {row["standard_index_name"]: row for row in rows}
        self.assertEqual(target["KOSPI200"]["current_value"], 355.44)
        self.assertEqual(target["KOSPI_FUTURES"]["current_value"], 354.8)
        self.assertEqual(target["USDKRW"]["current_value"], 1360.5)
        self.assertNotIn("잘못된 행", {row["index_name"] for row in rows})

    def test_parse_hankyung_program_html(self) -> None:
        collector = HankyungProgramTradingCollector()
        rows = collector.parse_with_pandas(SAMPLE_HANKYUNG_HTML, "2026-05-13", "2026-05-13T16:00:00+09:00")
        validation = validate_program_trading(rows)
        self.assertTrue(validation["valid"])
        target = {(row["market"], row["program_type"]): row for row in rows}
        self.assertEqual(target[("KOSPI", "ARBITRAGE")]["net_buy_value"], 17996)
        self.assertEqual(target[("KOSPI", "NON_ARBITRAGE")]["unit_value"], "백만원")
        self.assertEqual(target[("KOSPI", "ARBITRAGE")]["base_time_source"], "collected_at_fallback")

    def test_build_report_files(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "data" / "raw").mkdir(parents=True, exist_ok=True)
            save_json(
                root / "data" / "raw" / "kbsec_investor_trend_20260513.json",
                {"collected_at": "2026-05-13T10:00:00+09:00", "data": KBSECInvestorTrendCollector().parse_with_pandas(SAMPLE_KB_INVESTOR_HTML, "2026-05-13", "2026-05-13T10:00:00+09:00")},
            )
            save_json(
                root / "data" / "raw" / "kbsec_market_index_20260513.json",
                {"collected_at": "2026-05-13T10:00:00+09:00", "data": KBSECMarketIndexCollector().parse_with_pandas(SAMPLE_KB_INDEX_HTML, "2026-05-13", "2026-05-13T10:00:00+09:00")},
            )
            save_json(
                root / "data" / "raw" / "hankyung_program_trading_20260513.json",
                {"collected_at": "2026-05-13T16:00:00+09:00", "data": HankyungProgramTradingCollector().parse_with_pandas(SAMPLE_HANKYUNG_HTML, "2026-05-13", "2026-05-13T16:00:00+09:00")},
            )
            save_json(
                root / "data" / "raw" / "kis_index_futures_snapshot_20260513.json",
                {"collected_at": "2026-05-13T16:00:00+09:00", "data": [{
                    "futures_code": "A01606",
                    "futures_name": "F 202606",
                    "current_price": 1222.25,
                    "basis": 2.47,
                    "market_basis": 2.08,
                    "open_interest": 199628,
                    "open_interest_change": 6000,
                    "kospi200_index_value": 1220.17,
                    "token_source": "supabase_cache",
                }]},
            )
            save_json(
                root / "data" / "raw" / "kis_index_futures_daily_20260513.json",
                {"collected_at": "2026-05-13T16:00:00+09:00", "data": [{
                    "trade_date": "2026-05-13",
                    "futures_code": "A01606",
                    "open_price": 1160.0,
                    "high_price": 1223.4,
                    "low_price": 1144.5,
                    "close_price": 1222.25,
                    "accumulated_volume": 168145,
                    "accumulated_trading_value": 49938213275,
                }]},
            )
            files = build_derivatives_data_report(
                output_root=root,
                trade_date="2026-05-13",
                collection_results=[{"collector": "kbsec_investor_trend", "status": "success", "row_count": 4, "requests_success": True, "playwright_used": False, "error_message": None}],
                kis_auth_result={"status": "success", "config_path": "api_keys.json", "base_url": "https://openapi.koreainvestment.com:9443", "token_received": True, "expires_at": "2026-05-14T00:00:00+00:00", "error_message": None},
            )
            self.assertTrue(Path(files["markdown_report"]).exists())
            self.assertTrue(Path(files["json_packet"]).exists())
            self.assertTrue(Path(files["llm_input_text"]).exists())

    def test_validate_kis_futures(self) -> None:
        validation = validate_kis_futures([{
            "current_price": 1222.25,
            "market_basis": 2.08,
            "theoretical_basis": 2.47,
            "open_interest": 199628,
            "futures_code": "A01606",
            "futures_name": "F 202606",
        }])
        self.assertTrue(validation["valid"])


if __name__ == "__main__":
    unittest.main()
