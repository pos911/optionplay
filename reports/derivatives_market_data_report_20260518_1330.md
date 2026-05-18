# Derivatives Market Snapshot Report

## Warning

WARNING: This snapshot was collected 19 minutes after target_slot=1330. Use as delayed snapshot, not exact 13:30 data.

- trade_date: `2026-05-18`
- target_slot: `1330`
- actual_kst_time: `13:49`
- schedule_lag_minutes: `19`
- report_status: `DELAYED_LIVE`

## 오늘의 파생시장 한줄판단

지연 수집: 파생 수급은 전반적으로 하방 우위다.

## 판단 강도 점수

| score | value |
| --- | --- |
| futures_flow_score | 0 |
| options_flow_score | -2 |
| program_flow_score | -3 |
| fx_risk_score | 0 |
| composite_derivatives_score | -5 |

## 선물 수급 판단

외국인 선물 순매수는 1042, 미결제약정 변화는 1480, basis는 2.1, market_basis는 2.56로 선물 수급 점수는 0이다.

## 옵션 수급 판단

외국인 콜 순매수는 -55, 풋 순매수는 34로 옵션 해석은 하방 또는 헤지이며 옵션 점수는 -2이다.

## 프로그램매매 판단

KOSPI 차익은 68286, 비차익은 -1496114, 전체는 -1427829로 프로그램 점수는 -3이다.

## 지수 및 환율 환경

KOSPI 0.36%, KOSDAQ -1.74%, KOSPI200 0.77%, KOSPI futures 1.00%, USDKRW 0.20%, NASDAQ -1.54%, SP500 -1.24%. 환율 리스크 점수는 0이다.

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
| current_value | 1174.3 |
| change_value | 1.6 |
| change_rate | 1.00% |
| raw_change_text | ▲ 1.60 (1.00%) |
| inferred_product | KBSEC market page label KOSPI선물, detail link gbn=FUT, realtime feed KBRSFFC0 |
| semantics_confirmed | False |
| score_included | False |
| note | Source identifies this row as a futures item, but exact contract-month and change-rate semantics remain unconfirmed. |

## Market Index Focus

| standard_index_name | current_value | change_rate | direction | source_code | raw_change_text |
| --- | --- | --- | --- | --- | --- |
| KOSPI | 7520.26 | 0.36% | UP | KGG01P | ▲ 27.08 (0.36%) |
| KOSDAQ | 1110.13 | -1.74% | DOWN | QGG01P | ▼ 19.69 (1.74%) |
| KOSPI200 | 1171.39 | 0.77% | UP | K2G01P | ▲ 9.00 (0.77%) |
| KOSPI_FUTURES | 1174.3 | 1.00% | UP | A0166000 | ▲ 1.60 (1.00%) |
| NASDAQ | 26225.15 | -1.54% | DOWN | NAS@IXIC | ▼ 410.08 (1.54%) |
| SP500 | 7408.5 | -1.24% | DOWN | SPI@SPX | ▼ 92.74 (1.24%) |
| USDKRW | 1503.8 | 0.20% | UP | USDKRWSMBS | ▲ 3.00 (0.20%) |
