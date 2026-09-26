# 자동 회차 반영 계획

## 안전 원칙 (고정)

- **프로덕션 `.github/workflows/` 는 지금 단계에서는 수정하지 않는다**
- **`add-draw.yml` / 모바일 수동 입력 플로우는 절대 변경하지 않는다**
- 실험 산출물은 `auto-draw/` 안에만 둔다
- 메인 연결(승격)은 검증 후, **새 파일 추가**로만 한다 (기존 워크플로 편집 금지)

## 최종 원하는 그림

```text
[토 저녁 cron / Actions]
        │
        ▼
  manifest.latestDrawNo + 1 조회 (동행복권 API)
        │
        ├─ 미발표 → N분 대기 후 재조회 (여러 번)
        │            └─ 끝까지 없으면 skip 성공 (빨간 실패 X)
        │
        ├─ 번호 확보 → (검증 후) add_draw.py → Pages → FCM
        │               ※ 기존 수동 워크플로와 동일 스크립트 "호출만"
        │
        └─ API 변경/오류 → GitHub Issue 알림
                           └─ 개발자가 모바일에서 Add lotto draw 수동 실행
```

## Status

- [x] PC에서 내부 API 조회 OK (1241)
- [x] GitHub Actions 러너에서 동일 API OK (Probe workflow)
- [x] 로컬 확인용 앱 `check-app/` (조회·이력 UI)
- [x] `auto-draw/scripts/auto_draw_run.py` — 5분 재시도·Summary·누적 이력
- [x] `.github/workflows/auto-draw.yml` — **fetch only** (cron 토 20:45 KST, apply OFF)
- [x] Add / Fix 수동 워크플로 **유지** (미수정)
- [ ] 주말 cron dry-run 관찰 **2~3주**
- [ ] 안정화 후 **apply 연계** (조회 성공 → add_draw → Pages → FCM) — **별도 승인 후**
- [ ] apply 켜도 **Fix lotto draw / Add lotto draw 유지** (오탐·누락 폴백)

## 다음 단계 (2~3주 후 목표)

```text
토 20:45 cron
  → 5분 재시도로 번호 확보
  → (검증 기간 종료 후) add_draw.py → Pages → FCM 자동 반영
  → 번호 오류 시 모바일 Fix lotto draw (confirm=FIX)
  → API 실패 시 Issue → 수동 Add lotto draw
```

- apply 켜기 전: 지금처럼 **fetch only** + `FETCH_HISTORY.md`로 번호 대조  
- apply 켠 뒤에도 Fix/Add는 **삭제·비활성 금지**

## 재시도·알림 정책 (운용)

| 상황 | 동작 | Actions 결과 |
|------|------|----------------|
| cron 토 20:45 KST | job 기동 후 **5분 간격** 조회, 성공 시 중단 | — |
| 번호 확보 | Step Summary + `FETCH_HISTORY.md` 누적 커밋 | 성공 |
| 미발표 ~23:00대 | skip | 성공 |
| API/파싱 실패 | Issue + 수동 **Add/Fix** 안내 | 알림 job |
| 수동 폴백 | **Add lotto draw** / **Fix lotto draw** | **변경 없음** |

## Open questions

1. 2차 검증 소스 (당분간 단일 소스 + dry-run으로 갈지)
2. Issue assignee / 라벨 생성 권한
3. apply 켜기 전 dry-run 주수

## Decision log

| 날짜 | 내용 |
|------|------|
| 2026-09-16 | Probe 성공 → 자동화 기술적 가능. 별도 폴더 `auto-draw`에서 진행 |
| 2026-09-16 | 확인용 로컬 앱 `check-app` 추가 (GitHub 미연결) |
| 2026-09-16 | **의도 확정**: Actions 자동 조회 + 미발표 재시도 + API 실패 시 개발자 알림 → 수동 Add lotto draw |
| 2026-09-20 | cron 시작 **20:45 KST**로 변경 (5분 간격 유지) |
| 2026-09-20 | **합의**: 2~3주 fetch-only 관찰 후 apply(모바일 연계). Fix/Add는 apply 후에도 유지 |
| 2026-09-26 | 1243 추첨 22:30 지연. 20:45 예약 실행이 GitHub에서 생성되지 않음(누락) + 수동 Add 후엔 manifest+1(1244)을 찾는 구조라 이력 0건 |
| 2026-09-26 | 보완: 목표 회차를 날짜로 계산, 백업 cron(21:47/22:47/23:47/일 09:17), 이미 기록 시 skip, 최대 4시간, 수동 입력 대조 컬럼 추가 |
