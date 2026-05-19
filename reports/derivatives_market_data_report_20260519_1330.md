# Derivatives Market Snapshot Report

- trade_date: `2026-05-19`
- target_slot: `1330`
- actual_kst_time: `13:39`
- schedule_lag_minutes: `9`
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

외국인 선물 순매수는 -11086, 미결제약정 변화는 3828, basis는 1.94, market_basis는 1.34로 선물 수급 점수는 -1이다.

## 옵션 수급 판단

외국인 콜 순매수는 -215, 풋 순매수는 58로 옵션 해석은 하방 또는 헤지이며 옵션 점수는 -2이다.

## 프로그램매매 판단

KOSPI 차익은 86737, 비차익은 -3281127, 전체는 -3194389로 프로그램 점수는 -3이다.

## 지수 및 환율 환경

KOSPI -3.88%, KOSDAQ -3.68%, KOSPI200 -3.97%, KOSPI futures -1.04%, USDKRW 0.41%, NASDAQ -0.51%, SP500 -0.07%. 환율 리스크 점수는 -1이다.

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
| current_value | 1125.7 |
| change_value | -46.25 |
| change_rate | -1.04% |
| raw_change_text | ▼ 46.25 (1.04%) |
| inferred_product | KBSEC market page label KOSPI선물, detail link gbn=FUT, realtime feed KBRSFFC0 |
| semantics_confirmed | False |
| score_included | False |
| note | Source identifies this row as a futures item, but exact contract-month and change-rate semantics remain unconfirmed. |

## Market Index Focus

| standard_index_name | current_value | change_rate | direction | source_code | raw_change_text |
| --- | --- | --- | --- | --- | --- |
| KOSPI | 7224.38 | -3.88% | DOWN | KGG01P | ▼ 291.66 (3.88%) |
| KOSDAQ | 1070.2 | -3.68% | DOWN | QGG01P | ▼ 40.89 (3.68%) |
| KOSPI200 | 1124.76 | -3.97% | DOWN | K2G01P | ▼ 46.54 (3.97%) |
| KOSPI_FUTURES | 1125.7 | -1.04% | DOWN | A0166000 | ▼ 46.25 (1.04%) |
| NASDAQ | 26090.73 | -0.51% | DOWN | NAS@IXIC | ▼ 134.41 (0.51%) |
| SP500 | 7403.05 | -0.07% | DOWN | SPI@SPX | ▼ 5.45 (0.07%) |
| USDKRW | 1506.5 | 0.41% | UP | USDKRWSMBS | ▲ 6.20 (0.41%) |
