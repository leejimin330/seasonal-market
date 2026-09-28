# 제철 장바구니

이번 달 제철 농수산물의 현재 가격과 평년 대비 등락을 무료로 보여주고,
가격 추이와 판매처 유형별 비교(전통시장 vs 대형마트, 싼 지역)는 크레딧으로 여는 웹 서비스.
AI 웹 모음 플랫폼의 입점작 후보. 가격은 공공데이터포털의 aT 일별 소매가격 조사.

설계: `docs/superpowers/specs/2026-09-28-seasonal-market-design.md`

## 실행

`제철장바구니-서버-켜기.bat`을 더블클릭하면 서버가 뜨고 브라우저가 열린다 (http://127.0.0.1:8741).

직접 실행:

```
.venv\Scripts\python.exe -m uvicorn --factory app.main:build_default_app --port 8741
```

## 설정 (`.env`, 예시는 `.env.example`)

| 키 | 없으면 |
|---|---|
| `DATA_GO_KR_KEY` | 시세가 샘플 데이터 (공공데이터포털 "한국농수산식품유통공사_일별 도,소매 가격정보", 개인 자동승인) |
| `SEASONAL_ADMIN_USERS` | 관리자 화면 없음 |

키를 넣고 서버를 다시 켜면 샘플 가격은 지워지고, 최근 400일치를 먼저 받은 뒤
평년가 계산용 과거 5년치를 이어서 받는다(처음 한 번, 화면 하단에 진행 상황이 뜬다).
품목·품종·등급·단위는 `data/items.csv`에서 고른다. 코드표는 API 페이지의 "API명세 및 관련 코드정보.zip".

## 관리

```
.venv\Scripts\python.exe -m app.cli create-user <아이디> [--random]
.venv\Scripts\python.exe -m app.cli set-password <아이디>
.venv\Scripts\python.exe -m app.cli collect        가격 수집을 지금 한 번
```

크레딧 지급은 관리자 계정으로 로그인해 상단 `관리자` 화면에서 한다.

## 테스트

```
.venv\Scripts\python.exe -m pytest
```
