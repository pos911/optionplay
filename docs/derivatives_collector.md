# Derivatives Collector

## 목적

- 선물·옵션 수급으로 보는 시장상황 분석용 원천 데이터를 수집합니다.
- 이 레이어는 수집, 정규화, 파일 생성, LLM 입력 패킷 생성만 담당합니다.
- 시장 판단 로직, 매수/매도 의견, 투자 의견은 포함하지 않습니다.

## 수집 소스

- KB증권 투자자별 매매동향
- KB증권 지수정보
- 한경 프로그램 매매
- KIS 선물 스냅샷 및 KOSPI200 정규선물 프론트월 일봉

## GitHub Secret 설정

1. GitHub 저장소의 `Settings > Secrets and variables > Actions`로 이동합니다.
2. `New repository secret`를 클릭합니다.
3. Secret 이름을 `OPTIONPLAY_API_KEYS_JSON`으로 입력합니다.
4. Secret 값에는 로컬 `api_keys.json` 파일의 전체 내용을 그대로 넣습니다.

## GitHub Actions 실행 주기

- 평일 KST `07:20`부터 `17:20`까지 매시간 `20분`에 실행됩니다.
- 예약 트리거는 UTC cron으로 넓게 잡고, workflow 내부에서 `Asia/Seoul` 시간 가드를 다시 적용합니다.
- 한국시간 기준으로 평일이 아니거나 `07:20~17:20` 범위가 아니면 수집을 건너뜁니다.

## 수동 실행

- GitHub `Actions` 탭에서 `Collect Derivatives Market Data` workflow를 수동 실행할 수 있습니다.
- `commit_outputs` 입력값의 기본값은 `false`입니다.
- `commit_outputs=true`일 때만 `data/raw`와 `reports` 산출물을 커밋합니다.

## 실행 명령

```bash
python -m unittest tests.test_derivatives_collectors
python scripts/collect_derivatives_market_data.py --trade-date YYYY-MM-DD --output-root . --api-keys-path api_keys.json
```

## 산출물

- `data/raw`
- `reports`
- `logs`
- `debug`
- GitHub Actions artifact 이름: `derivatives-market-data-<run_id>`

## 보안 주의사항

- `api_keys.json`과 `config/api_keys.json`은 커밋하지 않습니다.
- KIS token 원문은 로그에 출력하지 않습니다.
- `debug/network`에는 token 원문 대신 `token_received`, `token_type`, `expires_at`, `token_source` 수준만 저장합니다.
- `commit_outputs=true`여도 `debug`, `logs`, `api_keys.json`, `.env`, `*.token`은 커밋 대상에 포함하지 않습니다.
