# Derivatives Market Snapshot Report

- trade_date: `2026-05-20`
- target_slot: `1330`
- actual_kst_time: `13:43`
- schedule_lag_minutes: `13`
- report_status: `LIVE`

## 오늘의 파생시장 한줄판단

파생 수급은 전반적으로 하방 우위다.

## 판단 강도 점수

| score | value |
| --- | --- |
| futures_flow_score | -1 |
| options_flow_score | -2 |
| program_flow_score | 0 |
| fx_risk_score | 0 |
| composite_derivatives_score | -3 |

## 선물 수급 판단

외국인 선물 순매수는 -5208, 미결제약정 변화는 3635, basis는 1.84, market_basis는 1.48로 선물 수급 점수는 -1이다.

## 옵션 수급 판단

외국인 콜 순매수는 -66, 풋 순매수는 43로 옵션 해석은 하방 또는 헤지이며 옵션 점수는 -2이다.

## 프로그램매매 판단

KOSPI 차익은 미수집, 비차익은 미수집, 전체는 미수집로 프로그램 점수는 0이다.

## 지수 및 환율 환경

KOSPI -1.86%, KOSDAQ -3.25%, KOSPI200 -1.68%, KOSPI futures -1.02%, USDKRW 0.12%, NASDAQ -0.84%, SP500 -0.67%. 환율 리스크 점수는 0이다.

## 다음 슬롯 체크포인트

다음 체크포인트는 14:30다. 외국인 선물 방향 지속 여부, 비차익 강도 변화, 콜/풋 방향 전환 여부를 확인한다.

## Data Quality Warnings

None

## Score Exclusions

None

## KOSPI_FUTURES Semantics

| field | value |
| --- | --- |
| source_code | A0166000 |
| index_name | KOSPI선물 |
| current_value | 1114.95 |
| change_value | -22.05 |
| change_rate | -1.02% |
| raw_change_text | ▼ 22.05 (1.02%) |
| inferred_product | KBSEC market page label KOSPI선물, detail link gbn=FUT, realtime feed KBRSFFC0 |
| semantics_confirmed | False |
| score_included | False |
| note | Source identifies this row as a futures item, but exact contract-month and change-rate semantics remain unconfirmed. |

## Market Index Focus

| standard_index_name | current_value | change_rate | direction | source_code | raw_change_text |
| --- | --- | --- | --- | --- | --- |
| KOSPI | 7136.61 | -1.86% | DOWN | KGG01P | ▼ 135.05 (1.86%) |
| KOSDAQ | 1049.1 | -3.25% | DOWN | QGG01P | ▼ 35.26 (3.25%) |
| KOSPI200 | 1113.38 | -1.68% | DOWN | K2G01P | ▼ 19.04 (1.68%) |
| KOSPI_FUTURES | 1114.95 | -1.02% | DOWN | A0166000 | ▼ 22.05 (1.02%) |
| NASDAQ | 25870.71 | -0.84% | DOWN | NAS@IXIC | ▼ 220.02 (0.84%) |
| SP500 | 7353.61 | -0.67% | DOWN | SPI@SPX | ▼ 49.44 (0.67%) |
| USDKRW | 1509.65 | 0.12% | UP | USDKRWSMBS | ▲ 1.85 (0.12%) |
