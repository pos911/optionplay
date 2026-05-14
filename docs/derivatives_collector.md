# Derivatives Collector

## Purpose

- Collect intraday derivatives source data needed for Korea options and futures interpretation.
- Generate raw packets, markdown reports, and LLM input text per `trade_date + target_slot`.
- Preserve retry-safe scheduled outputs without overwriting a healthy live slot result.

## Sources

- KBSEC investor trend
- KBSEC market index
- Hankyung program trading
- KIS index futures snapshot and daily futures data

## GitHub Secret

1. Open `Settings > Secrets and variables > Actions`.
2. Create `OPTIONPLAY_API_KEYS_JSON`.
3. Paste the full local `api_keys.json` content as the secret value.

## GitHub Actions Schedule

- Scheduled cron stays at `25,30,35,40 0-6 * * 1-5`.
- The KST guard maps these retry windows:
- `09:25~09:59 -> 0930`
- `10:25~10:59 -> 1030`
- `11:25~11:59 -> 1130`
- `12:25~12:59 -> 1230`
- `13:25~13:59 -> 1330`
- `14:25~14:59 -> 1430`
- `15:25~15:59 -> 1530`
- Any other time is skipped.

## Report Status Policy

- `schedule_lag_minutes <= 15`: `LIVE`
- `16 <= schedule_lag_minutes <= 59`: `DELAYED_LIVE`
- `schedule_lag_minutes >= 60`: `STALE_TEST_RUN`

## Manual Run

- `workflow_dispatch` accepts optional `trade_date`, `target_slot`, `commit_outputs`, and `force_overwrite`.
- If `target_slot` is omitted in `workflow_dispatch`, the workflow derives it from the current KST time using the same slot window rules.
- If manual execution starts outside every slot window and no explicit `target_slot` is provided, the run is skipped by the guard.

## Duplicate Slot Handling

- Existing files alone do not block a retry anymore.
- A scheduled or manual run is skipped only when the existing slot packet already has:
- `report_status` in `LIVE` or `DELAYED_LIVE`
- `kis_index_futures` collector status `success`
- If the existing packet is `STALE_TEST_RUN` or the core futures collector failed, overwrite is allowed.
- `force_overwrite=true` always overwrites.

## Scheduled Run Verification Checklist

1. Confirm the latest workflow run uses a commit at or after `d850c5c`.
2. If the scheduled run starts during KST `09:25~09:59`, confirm `target_slot=0930`.
3. Open `collection_summary.json` or the workflow summary and confirm `report_status` is `LIVE` or `DELAYED_LIVE`.
4. Confirm `schedule_lag_minutes <= 15` maps to `LIVE`, `16~59` maps to `DELAYED_LIVE`, and `>= 60` maps to `STALE_TEST_RUN`.
5. Confirm `reports/` and `data/raw/` contain files named with `YYYYMMDD_HHMM`.
6. If multiple retries fire for the same slot, confirm later retries print `slot already collected` after a healthy live packet already exists.

## Commands

```bash
python -m unittest discover -s tests -v
python scripts/collect_derivatives_market_data.py --trade-date YYYY-MM-DD --target-slot 1430 --output-root . --api-keys-path api_keys.json
```

## Outputs

- `data/raw`
- `reports`
- `logs`
- `debug`
- GitHub Actions artifact name: `derivatives-market-data-<run_id>-<trade_date>-<target_slot>`

## KOSPI_FUTURES Note

- `source_code=A0166000` is labeled as `KOSPI선물` in the KBSEC page.
- The page also links it through `gbn=FUT` and subscribes it to realtime feed `KBRSFFC0`.
- That is strong evidence this row is a futures product, but the exact contract-month and `change_rate` semantics are still treated as unconfirmed.
- When `KOSPI200` and `KOSPI_FUTURES` directions diverge sharply, the report flags the mismatch and excludes the `KOSPI_FUTURES change_rate` from score use.
