# auto-draw — 동행복권 자동 회차 반영 (별도 검토)

이 폴더는 `lotto-data` 메인 운영과 분리해서 **자동 업데이트 검토·실험**을 하기 위한 작업 공간입니다.  
Cursor에서 **이 폴더를 워크스페이스로 열고** Agent를 따로 실행하세요.

```text
C:\lotto-data\auto-draw
```

메인 운영 경로(`Add lotto draw` 수동 워크플로, Pages, FCM)는 **깨뜨리지 않는 것**이 원칙입니다.

---

## 목표

토요일 추첨 후 사람이 번호를 치지 않아도:

1. 동행복권에서 최신 회차 조회  
2. (권장) 교차검증  
3. 기존 `add_draw.py` → Pages → FCM 경로로 반영  

실패 시에는 지금처럼 모바일 GitHub 수동 폴백.

---

## 이미 확인된 사실 (2026-09-16)

| 항목 | 결과 |
|------|------|
| 레거시 `getLottoNumber` | 불가 (302) |
| 내부 API `selectPstLt645Info.do` | **PC·GitHub Actions 러너 모두 OK** |
| 1241 샘플 | `7,13,16,23,24,43` / 보너스 `9` / 일자 `20260912` |
| Probe 워크플로 | `lotto-data` repo: **Probe dhlottery API** (run success) |

API 예:

```text
GET https://www.dhlottery.co.kr/lt645/selectPstLt645Info.do?srchLtEpsd={회차}&_={ts}
Header: X-Requested-With: XMLHttpRequest
Header: Referer: https://www.dhlottery.co.kr/
```

응답 `data.list[0]`: `ltEpsd`, `tm1WnNo`~`tm6WnNo`, `bnsWnNo`, `ltRflYmd`

---

## 권장 설계 (초안)

1. **새 워크플로만 추가** (`auto-draw.yml`) — 기존 `add-draw.yml`은 유지  
2. cron 여러 번 (토 20:50 / 21:10 / 21:40 / 22:30 KST 상당)  
3. `manifest.latestDrawNo + 1` 조회 → 미발표면 **skip(성공 종료)**  
4. 가능하면 2차 소스와 번호 일치할 때만 커밋  
5. 기존 `scripts/add_draw.py` 호출 → Pages → FCM  
6. 실패/불일치 시 이슈 또는 알림 (조용한 실패 금지)

스키마는 그대로: `{drawNo, win6, bonus}` → `draws_v3.json` / `manifest.json`

---

## 폴더 구조

```text
auto-draw/
  README.md          ← 이 파일
  AGENTS.md          ← Agent 시작용 지시
  docs/
    PLAN.md          ← 상세 계획 (수정하며 사용)
  scripts/           ← 실험용 스크립트 (검증 후 루트 scripts/로 승격)
  check-app/         ← 번호 확인용 로컬 웹앱 (시안 구현)
  notes/             ← 실험 로그·메모
```

### 확인용 앱 실행

```text
python check-app/server.py
# → http://127.0.0.1:8765
```

- 토요일 20:45(KST) 이후(및 일요일): 자동 조회
- 그 외: 대기 화면 + `지금 조회 (테스트)`로 강제 조회

---

## 관련 경로

| 용도 | 경로 |
|------|------|
| 데이터 repo 루트 | `C:\lotto-data` |
| 앱 | `C:\lotto_wizard` |
| 수동 업데이트 가이드 | `C:\lotto_wizard\docs\ops\MOBILE_DRAW_UPDATE.md` |
| FCM | `C:\lotto_wizard\docs\ops\FIREBASE_FCM_SETUP.md` |
| Probe 워크플로 | `C:\lotto-data\.github\workflows\probe-dhlottery.yml` |
| 수동 추가 | `C:\lotto-data\.github\workflows\add-draw.yml` |
| 추가 스크립트 | `C:\lotto-data\scripts\add_draw.py` |

---

## 주의

- 동행복권 엔드포인트는 **비공식** — 언제든 변경 가능  
- 잘못된 번호 + FCM = 사용자 알림 오발송 — 교차검증 권장  
- **Add lotto draw / Fix lotto draw 는 유지** (수정·대체 금지)  
- auto-draw는 현재 **조회 전용(apply OFF)** — 엑셀/Pages/FCM 미반영

---

## Auto draw (fetch only) — 운용 중 설계

1. 토 **20:45 KST** cron → `latestDrawNo+1` 조회  
2. 미발표면 **5분마다** 재시도, 성공 시 중단 (~23:00까지)  
3. Job Summary에 **가져온 번호** 표시 + `auto-draw/data/FETCH_HISTORY.md` 누적  
4. API 실패 시 Issue → 모바일 **Add** / **Fix** 폴백  
5. apply(엑셀/Pages/FCM)는 **아직 없음**

프로덕션 파일:

- `.github/workflows/auto-draw.yml` (신규, Add/Fix와 분리)  
- `auto-draw/scripts/auto_draw_run.py`  
- `auto-draw/data/FETCH_HISTORY.md` / `fetch_history.json`
