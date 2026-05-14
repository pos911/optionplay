from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from collectors.derivatives.common import build_slot_suffix, resolve_target_slot_for_timestamp
from collectors.derivatives.kbsec_market_index_collector import KBSECMarketIndexCollector
from collectors.derivatives.report_builder import build_derivatives_data_report
from collectors.derivatives.validators import validate_market_index
from scripts.collect_derivatives_market_data import build_output_paths, should_skip_existing_outputs


class TestTargetSlotWindow(unittest.TestCase):
    def test_target_slot_calculation(self) -> None:
        cases = {
            "2026-05-14T09:25:00+09:00": "0930",
            "2026-05-14T09:30:00+09:00": "0930",
            "2026-05-14T09:58:00+09:00": "0930",
            "2026-05-14T10:59:00+09:00": "1030",
            "2026-05-14T11:00:00+09:00": None,
            "2026-05-14T15:58:00+09:00": "1530",
            "2026-05-14T16:00:00+09:00": None,
        }
        for timestamp, expected in cases.items():
            with self.subTest(timestamp=timestamp):
                self.assertEqual(resolve_target_slot_for_timestamp(timestamp), expected)


class TestOutputPathsAndDuplicateSkip(unittest.TestCase):
    def test_build_slot_suffix(self) -> None:
        self.assertEqual(build_slot_suffix("2026-05-14", "1430"), "20260514_1430")

    def test_output_files_include_slot(self) -> None:
        output_paths = build_output_paths(Path("."), "2026-05-14", "1430")
        for path in output_paths.values():
            self.assertIn("20260514_1430", path.name)

    def test_existing_live_packet_skips(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            output_paths = build_output_paths(root, "2026-05-14", "1430")
            output_paths["json_packet"].parent.mkdir(parents=True, exist_ok=True)
            output_paths["json_packet"].write_text(
                json.dumps(
                    {
                        "report_status": "LIVE",
                        "collection_status": [
                            {"collector": "kis_index_futures", "status": "success"},
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            self.assertTrue(should_skip_existing_outputs(output_paths, force_overwrite=False))

    def test_existing_stale_packet_allows_overwrite(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            output_paths = build_output_paths(root, "2026-05-14", "1430")
            output_paths["json_packet"].parent.mkdir(parents=True, exist_ok=True)
            output_paths["json_packet"].write_text(
                json.dumps(
                    {
                        "report_status": "STALE_TEST_RUN",
                        "collection_status": [
                            {"collector": "kis_index_futures", "status": "success"},
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            self.assertFalse(should_skip_existing_outputs(output_paths, force_overwrite=False))

    def test_force_overwrite_bypasses_skip(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            output_paths = build_output_paths(root, "2026-05-14", "1430")
            output_paths["json_packet"].parent.mkdir(parents=True, exist_ok=True)
            output_paths["json_packet"].write_text("{}", encoding="utf-8")
            self.assertFalse(should_skip_existing_outputs(output_paths, force_overwrite=True))


class TestKBSECMarketIndexCollector(unittest.TestCase):
    def test_malformed_numeric_strings_do_not_crash(self) -> None:
        html = """
        <html><body>
        <table><tbody id="stockKr">
          <tr data-code="KGG01P"><th>코스피종합</th><td>0.000.00</td><td>▲ 137.40 (1.75%)</td></tr>
          <tr data-code="K2G01P"><th>코스피200</th><td>1,243.17</td><td>▲ 23.00 (1.88%)</td></tr>
          <tr><th>2026-6</th><td>1,111.11</td><td>▲ 1.00 (0.10%)</td></tr>
        </tbody></table>
        <table><tbody id="stockEng">
          <tr data-code="NAS@IXIC"><th>NASDAQ</th><td>-</td><td> </td></tr>
        </tbody></table>
        <table><tbody id="stockEtc">
          <tr data-code="USDKRWSMBS"><th>원달러</th><td>1,491.20</td><td>▲ 0.60 (0.04%)</td></tr>
        </tbody></table>
        </body></html>
        """
        collector = KBSECMarketIndexCollector()
        rows, skipped_rows = collector.parse_with_bs4(html, "2026-05-14", "2026-05-14T14:30:00+09:00")
        self.assertGreaterEqual(skipped_rows, 2)
        self.assertTrue(any(row["standard_index_name"] == "KOSPI200" for row in rows))
        self.assertTrue(any(row["standard_index_name"] == "USDKRW" for row in rows))

    def test_partial_rows_still_success_after_validation(self) -> None:
        collector = KBSECMarketIndexCollector()
        html = """
        <html><body>
        <table><tbody id="stockKr">
          <tr data-code="K2G01P"><th>코스피200</th><td>1,243.17</td><td>▲ 23.00 (1.88%)</td></tr>
          <tr data-code="A0166000"><th>KOSPI선물</th><td>1,232.60</td><td>▼ 12.90 (1.01%)</td></tr>
        </tbody></table>
        <table><tbody id="stockEng">
          <tr data-code="SPI@SPX"><th>S&P 500</th><td>7,480.05</td><td>▲ 35.80 (0.48%)</td></tr>
        </tbody></table>
        <table><tbody id="stockEtc">
          <tr data-code="USDKRWSMBS"><th>원달러</th><td>1,491.20</td><td>▲ 0.60 (0.04%)</td></tr>
          <tr><th>2026-6</th><td>1,491.20</td><td>▲ 0.60 (0.04%)</td></tr>
        </tbody></table>
        </body></html>
        """
        rows, skipped_rows = collector.parse_with_bs4(html, "2026-05-14", "2026-05-14T14:30:00+09:00")
        validation = validate_market_index(rows)
        self.assertTrue(validation["valid"])
        self.assertEqual(skipped_rows, 1)
        futures_row = next(row for row in rows if row["standard_index_name"] == "KOSPI_FUTURES")
        self.assertEqual(futures_row["raw_data"]["change_rate"], -1.01)
        self.assertEqual(futures_row["source_fields"]["detail_group"], "FUT")


class TestReportBuilder(unittest.TestCase):
    def _write_payload(self, path: Path, payload: dict[str, object]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def _prepare_payloads(
        self,
        root: Path,
        *,
        lag_minutes: int,
        futures_score_case: str = "mixed",
        missing_rates: bool = False,
        divergent_rates: bool = False,
        kbsec_index_failed: bool = False,
    ) -> None:
        suffix = "20260514_1430"
        common_meta = {
            "trade_date": "2026-05-14",
            "target_slot": "1430",
            "generated_at": "2026-05-14T14:59:00+09:00",
            "collected_at": "2026-05-14T14:59:00+09:00",
            "actual_kst_time": "14:59",
            "schedule_lag_minutes": lag_minutes,
            "market_session": "REGULAR",
            "source_time": "14:30",
            "base_time": "14:30",
            "base_time_source": "target_slot",
            "status": "success",
            "validation": {"valid": True, "errors": [], "row_count": 1},
        }
        futures_net = -12000 if futures_score_case in {"mixed", "negative"} else 12000
        program_total = 6000 if futures_score_case in {"mixed", "positive"} else -6000

        self._write_payload(
            root / "data" / "raw" / f"kbsec_investor_trend_{suffix}.json",
            {
                **common_meta,
                "source": "KBSEC",
                "source_url": "https://example.com/investor",
                "data": [
                    {"trade_date": "2026-05-14", "target_slot": "1430", "category": "KOSPI200_FUTURES", "foreigner_net_buy": futures_net, "individual_net_buy": 3000, "institution_net_buy": 12000},
                    {"trade_date": "2026-05-14", "target_slot": "1430", "category": "KOSPI200_CALL_OPTIONS", "foreigner_net_buy": 310, "individual_net_buy": -100, "institution_net_buy": -210},
                    {"trade_date": "2026-05-14", "target_slot": "1430", "category": "KOSPI200_PUT_OPTIONS", "foreigner_net_buy": 7, "individual_net_buy": 20, "institution_net_buy": -27},
                ],
            },
        )

        index_rows = [
            {"standard_index_name": "KOSPI", "current_value": 2700.1, "change_rate": None if missing_rates else -0.8, "direction": "DOWN", "source_code": "KGG01P", "raw_change_text": "▲ 137.40 (1.75%)"},
            {"standard_index_name": "KOSDAQ", "current_value": 820.0, "change_rate": None if missing_rates else -1.0, "direction": "DOWN", "source_code": "QGG01P", "raw_change_text": "▲ 14.16 (1.20%)"},
            {"standard_index_name": "KOSPI200", "current_value": 355.4, "change_rate": 1.88 if divergent_rates else -0.9, "direction": "UP" if divergent_rates else "DOWN", "source_code": "K2G01P", "raw_change_text": "▲ 23.00 (1.88%)"},
            {
                "standard_index_name": "KOSPI_FUTURES",
                "index_name": "KOSPI선물",
                "current_value": 354.8,
                "change_value": -3.6,
                "change_rate": -1.01 if divergent_rates else -1.1,
                "direction": "DOWN",
                "source_code": "A0166000",
                "raw_current_value_text": "354.8",
                "raw_change_text": "▼ 3.60 (1.01%)",
                "raw_data": {
                    "source_code": "A0166000",
                    "current_value": 354.8,
                    "change_value": -3.6,
                    "change_rate": -1.01 if divergent_rates else -1.1,
                },
                "source_fields": {
                    "data_code": "A0166000",
                    "detail_group": "FUT",
                    "realtime_feed_hint": "KBRSFFC0",
                },
            },
            {"standard_index_name": "USDKRW", "current_value": 1360.5, "change_rate": 0.35, "direction": "UP", "source_code": "USDKRWSMBS", "raw_change_text": "▲ 0.60 (0.04%)"},
            {"standard_index_name": "NASDAQ", "current_value": 18001.2, "change_rate": None if missing_rates else 0.56, "direction": "UP", "source_code": "NAS@IXIC", "raw_change_text": "▲ 37.09 (0.14%)"},
            {"standard_index_name": "SP500", "current_value": 5300.0, "change_rate": 0.42, "direction": "UP", "source_code": "SPI@SPX", "raw_change_text": "▲ 35.80 (0.48%)"},
        ]
        self._write_payload(
            root / "data" / "raw" / f"kbsec_market_index_{suffix}.json",
            {
                **common_meta,
                "status": "failed" if kbsec_index_failed else "success",
                "source": "KBSEC",
                "source_url": "https://example.com/index",
                "data": [] if kbsec_index_failed else index_rows,
            },
        )

        self._write_payload(
            root / "data" / "raw" / f"hankyung_program_trading_{suffix}.json",
            {
                **common_meta,
                "source": "HANKYUNG",
                "source_url": "https://example.com/program",
                "data": [
                    {"trade_date": "2026-05-14", "market": "KOSPI", "program_type": "ARBITRAGE", "net_buy_value": 1000, "unit_value": "백만원"},
                    {"trade_date": "2026-05-14", "market": "KOSPI", "program_type": "NON_ARBITRAGE", "net_buy_value": 5000, "unit_value": "백만원"},
                    {"trade_date": "2026-05-14", "market": "KOSPI", "program_type": "TOTAL", "net_buy_value": program_total, "unit_value": "백만원"},
                ],
            },
        )

        self._write_payload(
            root / "data" / "raw" / f"kis_index_futures_snapshot_{suffix}.json",
            {
                **common_meta,
                "source": "KIS",
                "source_url": "https://example.com/futures-snapshot",
                "data": [{"futures_name": "F 202606", "basis": -1.2, "market_basis": -0.4, "open_interest": 199628, "open_interest_change": 6000}],
            },
        )

        self._write_payload(
            root / "data" / "raw" / f"kis_index_futures_daily_{suffix}.json",
            {
                **common_meta,
                "source": "KIS",
                "source_url": "https://example.com/futures-daily",
                "data": [{"trade_date": "2026-05-14", "futures_code": "A01606", "close_price": 1222.25}],
            },
        )

    def test_report_status_thresholds(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._prepare_payloads(root, lag_minutes=10)
            files = build_derivatives_data_report(
                output_root=root,
                trade_date="2026-05-14",
                target_slot="1430",
                collected_at="2026-05-14T14:40:00+09:00",
                collection_results=[{"collector": "kbsec_market_index", "status": "success"}, {"collector": "kis_index_futures", "status": "success"}],
                kis_auth_result={"status": "success"},
            )
            packet = json.loads(Path(files["json_packet"]).read_text(encoding="utf-8"))
            self.assertEqual(packet["report_status"], "LIVE")

        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._prepare_payloads(root, lag_minutes=35)
            files = build_derivatives_data_report(
                output_root=root,
                trade_date="2026-05-14",
                target_slot="1430",
                collected_at="2026-05-14T15:05:00+09:00",
                collection_results=[{"collector": "kbsec_market_index", "status": "success"}, {"collector": "kis_index_futures", "status": "success"}],
                kis_auth_result={"status": "success"},
            )
            packet = json.loads(Path(files["json_packet"]).read_text(encoding="utf-8"))
            self.assertEqual(packet["report_status"], "DELAYED_LIVE")
            self.assertTrue(packet["one_line_judgement"].startswith("지연 수집: "))

        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._prepare_payloads(root, lag_minutes=536)
            files = build_derivatives_data_report(
                output_root=root,
                trade_date="2026-05-14",
                target_slot="1430",
                collected_at="2026-05-14T23:26:00+09:00",
                collection_results=[{"collector": "kbsec_market_index", "status": "success"}, {"collector": "kis_index_futures", "status": "success"}],
                kis_auth_result={"status": "success"},
            )
            packet = json.loads(Path(files["json_packet"]).read_text(encoding="utf-8"))
            self.assertEqual(packet["report_status"], "STALE_TEST_RUN")
            self.assertIn("장중 판단에는 부적합", packet["one_line_judgement"])

    def test_none_percent_is_not_rendered(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._prepare_payloads(root, lag_minutes=10, missing_rates=True)
            files = build_derivatives_data_report(
                output_root=root,
                trade_date="2026-05-14",
                target_slot="1430",
                collected_at="2026-05-14T14:40:00+09:00",
                collection_results=[{"collector": "kbsec_market_index", "status": "success"}, {"collector": "kis_index_futures", "status": "success"}],
                kis_auth_result={"status": "success"},
            )
            report_text = Path(files["markdown_report"]).read_text(encoding="utf-8")
            self.assertNotIn("None%", report_text)
            self.assertIn("데이터 없음", report_text)

    def test_conflicting_scores_produce_mixed_judgement(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._prepare_payloads(root, lag_minutes=10, futures_score_case="mixed")
            files = build_derivatives_data_report(
                output_root=root,
                trade_date="2026-05-14",
                target_slot="1430",
                collected_at="2026-05-14T14:40:00+09:00",
                collection_results=[{"collector": "kbsec_market_index", "status": "success"}, {"collector": "kis_index_futures", "status": "success"}],
                kis_auth_result={"status": "success"},
            )
            packet = json.loads(Path(files["json_packet"]).read_text(encoding="utf-8"))
            self.assertIn("혼조", packet["one_line_judgement"])

    def test_data_quality_warning_and_score_exclusion_for_divergent_rates(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._prepare_payloads(root, lag_minutes=10, divergent_rates=True)
            files = build_derivatives_data_report(
                output_root=root,
                trade_date="2026-05-14",
                target_slot="1430",
                collected_at="2026-05-14T14:40:00+09:00",
                collection_results=[{"collector": "kbsec_market_index", "status": "success"}, {"collector": "kis_index_futures", "status": "success"}],
                kis_auth_result={"status": "success"},
            )
            packet = json.loads(Path(files["json_packet"]).read_text(encoding="utf-8"))
            self.assertTrue(packet["data_quality_warnings"])
            self.assertIn("diverge sharply", packet["data_quality_warnings"][0])
            self.assertTrue(packet["score_exclusions"])
            self.assertIn("excluded from score calculation", packet["score_exclusions"][0])
            self.assertFalse(packet["instrument_semantics"]["KOSPI_FUTURES"]["score_included"])

    def test_report_is_generated_when_kbsec_market_index_failed(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._prepare_payloads(root, lag_minutes=20, kbsec_index_failed=True)
            files = build_derivatives_data_report(
                output_root=root,
                trade_date="2026-05-14",
                target_slot="1430",
                collected_at="2026-05-14T14:50:00+09:00",
                collection_results=[{"collector": "kbsec_market_index", "status": "failed"}, {"collector": "kis_index_futures", "status": "success"}],
                kis_auth_result={"status": "success"},
            )
            packet = json.loads(Path(files["json_packet"]).read_text(encoding="utf-8"))
            self.assertTrue(Path(files["markdown_report"]).exists())
            self.assertIn("KBSEC 시장지수 수집 실패로 지수/환율 판단 신뢰도 낮음", packet["warning"])


if __name__ == "__main__":
    unittest.main()
