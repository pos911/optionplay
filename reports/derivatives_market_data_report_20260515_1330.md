# Derivatives Market Snapshot Report

- trade_date: `2026-05-15`
- target_slot: `1330`
- actual_kst_time: `13:34`
- schedule_lag_minutes: `4`
- report_status: `LIVE`

## 오늘의 파생시장 한줄판단

파생 수급은 전반적으로 하방 우위다.

## 판단 강도 점수

| score | value |
| --- | --- |
| futures_flow_score | -1 |
| options_flow_score | -2 |
| program_flow_score | -3 |
| fx_risk_score | -1 |
| composite_derivatives_score | -7 |

## 선물 수급 판단

외국인 선물 순매수는 -7889, 미결제약정 변화는 2301, basis는 2.13, market_basis는 1.52로 선물 수급 점수는 -1이다.

## 옵션 수급 판단

외국인 콜 순매수는 -250, 풋 순매수는 99로 옵션 해석은 하방 또는 헤지이며 옵션 점수는 -2이다.

## 프로그램매매 판단

KOSPI 차익은 95979, 비차익은 -3204049, 전체는 -3108070로 프로그램 점수는 -3이다.

## 지수 및 환율 환경

KOSPI -4.88%, KOSDAQ -4.04%, KOSPI200 -5.15%, KOSPI futures -1.05%, USDKRW 0.43%, NASDAQ 0.88%, SP500 0.77%. 환율 리스크 점수는 -1이다.

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
| current_value | 1180.9 |
| change_value | -64.6 |
| change_rate | -1.05% |
| raw_change_text | ▼ 64.60 (1.05%) |
| inferred_product | KBSEC market page label KOSPI선물, detail link gbn=FUT, realtime feed KBRSFFC0 |
| semantics_confirmed | False |
| score_included | False |
| note | Source identifies this row as a futures item, but exact contract-month and change-rate semantics remain unconfirmed. |

## Market Index Focus

| standard_index_name | current_value | change_rate | direction | source_code | raw_change_text |
| --- | --- | --- | --- | --- | --- |
| KOSPI | 7591.82 | -4.88% | DOWN | KGG01P | ▼ 389.59 (4.88%) |
| KOSDAQ | 1143 | -4.04% | DOWN | QGG01P | ▼ 48.09 (4.04%) |
| KOSPI200 | 1179.15 | -5.15% | DOWN | K2G01P | ▼ 64.02 (5.15%) |
| KOSPI_FUTURES | 1180.9 | -1.05% | DOWN | A0166000 | ▼ 64.60 (1.05%) |
| NASDAQ | 26635.22 | 0.88% | UP | NAS@IXIC | ▲ 232.88 (0.88%) |
| SP500 | 7501.24 | 0.77% | UP | SPI@SPX | ▲ 56.99 (0.77%) |
| USDKRW | 1497.4 | 0.43% | UP | USDKRWSMBS | ▲ 6.40 (0.43%) |
