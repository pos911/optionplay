# Derivatives Market Snapshot Report

## Warning

WARNING: This snapshot was collected 19 minutes after target_slot=1030. Use as delayed snapshot, not exact 10:30 data.

- trade_date: `2026-05-15`
- target_slot: `1030`
- actual_kst_time: `10:49`
- schedule_lag_minutes: `19`
- report_status: `DELAYED_LIVE`

## 오늘의 파생시장 한줄판단

지연 수집: 선물 상방 압력과 프로그램 매도가 충돌하는 혼조 구간이다.

## 판단 강도 점수

| score | value |
| --- | --- |
| futures_flow_score | 1 |
| options_flow_score | -2 |
| program_flow_score | -3 |
| fx_risk_score | -1 |
| composite_derivatives_score | -5 |

## 선물 수급 판단

외국인 선물 순매수는 -2291, 미결제약정 변화는 590, basis는 2.21, market_basis는 1.2로 선물 수급 점수는 1이다.

## 옵션 수급 판단

외국인 콜 순매수는 -144, 풋 순매수는 12로 옵션 해석은 하방 또는 헤지이며 옵션 점수는 -2이다.

## 프로그램매매 판단

KOSPI 차익은 33387, 비차익은 -847675, 전체는 -814287로 프로그램 점수는 -3이다.

## 지수 및 환율 환경

KOSPI -1.66%, KOSDAQ -1.99%, KOSPI200 -1.78%, KOSPI futures -1.02%, USDKRW 0.55%, NASDAQ 0.88%, SP500 0.77%. 환율 리스크 점수는 -1이다.

## 다음 슬롯 체크포인트

다음 체크포인트는 11:30다. 외국인 선물 방향 지속 여부, 비차익 강도 변화, 콜/풋 방향 전환 여부를 확인한다.

## Data Quality Warnings

None

## Score Exclusions

None

## KOSPI_FUTURES Semantics

| field | value |
| --- | --- |
| source_code | A0166000 |
| index_name | KOSPI선물 |
| current_value | 1222 |
| change_value | -23.5 |
| change_rate | -1.02% |
| raw_change_text | ▼ 23.50 (1.02%) |
| inferred_product | KBSEC market page label KOSPI선물, detail link gbn=FUT, realtime feed KBRSFFC0 |
| semantics_confirmed | False |
| score_included | False |
| note | Source identifies this row as a futures item, but exact contract-month and change-rate semantics remain unconfirmed. |

## Market Index Focus

| standard_index_name | current_value | change_rate | direction | source_code | raw_change_text |
| --- | --- | --- | --- | --- | --- |
| KOSPI | 7849.14 | -1.66% | DOWN | KGG01P | ▼ 132.27 (1.66%) |
| KOSDAQ | 1167.39 | -1.99% | DOWN | QGG01P | ▼ 23.70 (1.99%) |
| KOSPI200 | 1221.08 | -1.78% | DOWN | K2G01P | ▼ 22.09 (1.78%) |
| KOSPI_FUTURES | 1222 | -1.02% | DOWN | A0166000 | ▼ 23.50 (1.02%) |
| NASDAQ | 26635.22 | 0.88% | UP | NAS@IXIC | ▲ 232.88 (0.88%) |
| SP500 | 7501.24 | 0.77% | UP | SPI@SPX | ▲ 56.99 (0.77%) |
| USDKRW | 1499.25 | 0.55% | UP | USDKRWSMBS | ▲ 8.25 (0.55%) |
