# Derivatives Market Snapshot Report

## Warning

WARNING: This snapshot was collected 21 minutes after target_slot=1330. Use as delayed snapshot, not exact 13:30 data.

- trade_date: `2026-05-21`
- target_slot: `1330`
- actual_kst_time: `13:51`
- schedule_lag_minutes: `21`
- report_status: `DELAYED_LIVE`

## 오늘의 파생시장 한줄판단

지연 수집: 파생 수급은 전반적으로 상방 우위다.

## 판단 강도 점수

| score | value |
| --- | --- |
| futures_flow_score | 2 |
| options_flow_score | 3 |
| program_flow_score | 3 |
| fx_risk_score | 0 |
| composite_derivatives_score | 8 |

## 선물 수급 판단

외국인 선물 순매수는 11259, 미결제약정 변화는 -1469, basis는 1.92, market_basis는 1.88로 선물 수급 점수는 2이다.

## 옵션 수급 판단

외국인 콜 순매수는 164, 풋 순매수는 -3로 옵션 해석은 상방 베팅이며 옵션 점수는 3이다.

## 프로그램매매 판단

KOSPI 차익은 187945, 비차익은 926078, 전체는 1114022로 프로그램 점수는 3이다.

## 지수 및 환율 환경

KOSPI 8.07%, KOSDAQ 5.06%, KOSPI200 8.47%, KOSPI futures 1.08%, USDKRW -0.13%, NASDAQ 1.54%, SP500 1.08%. 환율 리스크 점수는 0이다.

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
| current_value | 1223.2 |
| change_value | 97.25 |
| change_rate | 1.08% |
| raw_change_text | ▲ 97.25 (1.08%) |
| inferred_product | KBSEC market page label KOSPI선물, detail link gbn=FUT, realtime feed KBRSFFC0 |
| semantics_confirmed | False |
| score_included | False |
| note | Source identifies this row as a futures item, but exact contract-month and change-rate semantics remain unconfirmed. |

## Market Index Focus

| standard_index_name | current_value | change_rate | direction | source_code | raw_change_text |
| --- | --- | --- | --- | --- | --- |
| KOSPI | 7790.73 | 8.07% | UP | KGG01P | ▲ 581.78 (8.07%) |
| KOSDAQ | 1109.55 | 5.06% | UP | QGG01P | ▲ 53.48 (5.06%) |
| KOSPI200 | 1220.89 | 8.47% | UP | K2G01P | ▲ 95.38 (8.47%) |
| KOSPI_FUTURES | 1223.2 | 1.08% | UP | A0166000 | ▲ 97.25 (1.08%) |
| NASDAQ | 26270.36 | 1.54% | UP | NAS@IXIC | ▲ 399.65 (1.54%) |
| SP500 | 7432.97 | 1.08% | UP | SPI@SPX | ▲ 79.36 (1.08%) |
| USDKRW | 1504.9 | -0.13% | DOWN | USDKRWSMBS | ▼ 1.90 (0.13%) |
