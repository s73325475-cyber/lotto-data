# Auto draw → 자동 푸시(apply) 연계 가이드

> **현재(2026-10-16):** apply **완전 자동 ON** (cron 포함). 조회 성공 → add_draw → Pages → FCM.  
> **폴백:** 실패 시 모바일 **Add lotto draw** / **Fix lotto draw** (워크플로 유지).

관련 문서:

| 문서 | 용도 |
|------|------|
| [PLAN.md](./PLAN.md) | 설계·결정 로그 |
| [AGENT_PROMPT_APPLY.md](./AGENT_PROMPT_APPLY.md) | Cursor Agent에 붙여 넣을 구현 프롬프트 |
| `C:\lotto_wizard\docs\ops\AUTO_DRAW_APPLY_APP_CHECK.md` | 앱(로또 위자드) 측 확인 — **대개 코드 변경 불필요** |
| `C:\lotto_wizard\docs\ops\MOBILE_DRAW_UPDATE.md` | 수동 Add/Fix 모바일 절차 |
| `C:\lotto_wizard\docs\ops\FIREBASE_FCM_SETUP.md` | FCM 시크릿·토픽 |

---

## 1. 최종 흐름 (켜고 싶은 그림)

```text
[토 저녁 Auto draw cron / relay]
        │
        ▼
  동행복권 API → 번호 확보
        │
        ├─ FETCH_HISTORY 커밋 (검증 이력, 지금과 동일)
        │
        ├─ [APPLY ON] add_draw.py
        │       → excel / draws_v3 / manifest 커밋
        │       → GitHub Pages 배포
        │       → FCM topic `draw_data` (type=draw_data_ready)
        │
        └─ 앱(로또 위자드)
                → FCM으로 깨움 → Pages sync → 보관함 대조 → 로컬 알림
```

**앱 쪽:** 이미 `draw_data` 토픽 + `DrawWinPushSync` 경로가 있다.  
apply를 켜도 **페이로드 계약이 같으면 앱 수정은 보통 0건**이다.

---

## 2. 켜기 전 체크리스트 (권장 순서)

### A. fetch-only 관찰

- [x] 1243 조회 + 수동 일치
- [x] 1244 조회 + 수동 일치
- [x] 1245 조회 성공 (조회 시점 미입력 → 직후 Add와 번호 동일)

### B. apply 구현

- [x] `auto-draw.yml` apply job (add_draw → Pages → FCM)
- [x] **cron apply ON** / dispatch `apply` 기본 true
- [x] 불일치 시 apply 금지, 이미 latest면 스킵
- [x] `skip_fcm` 입력 (시험용)

### C. 인프라·폴백

- [ ] Secrets `FIREBASE_SERVICE_ACCOUNT_JSON` (없으면 FCM만 경고·스킵)
- [x] Add / Fix 워크플로 미수정·폴백 유지

---

## 3. 구현 방식 (권장)

**기존 `auto-draw.yml`에 apply 단계를 추가**하되, **기본은 OFF**로 두고 입력/시크릿으로 켠다.

| 방식 | 장점 | 단점 |
|------|------|------|
| **A. 같은 워크플로 + `apply: true` 입력** (권장) | cron·relay·이력 재사용 | 파일 한 곳에 로직 모임 |
| B. 새 `auto-draw-apply.yml` | 분리 명확 | 스케줄·이력 중복 |
| C. fetch 성공 후 `gh workflow run add-draw.yml -f ...` | Add 경로 그대로 | 입력 전달·권한·race 관리 필요 |

권장 상세 (A):

1. fetch `outcome=ready` 이고 `manual_match != 불일치` 일 때만 apply 후보  
2. 이미 `manifest.latestDrawNo >= drawNo` 이면 apply **skip** (수동 Add가 먼저 끝난 경우)  
3. apply 시 **기존과 동일 스크립트만 호출**:

```bash
python scripts/add_draw.py \
  --draw-no "$DRAW_NO" \
  --numbers "$NUMBERS" \
  --bonus "$BONUS" \
  --repo-root . \
  --version 3
```

4. 그다음 Add 워크플로와 같은 순서로: commit → Pages artifact → deploy-pages → `send_fcm_draw_data.py`  
5. concurrency: fetch는 `auto-draw-fetch`, apply(커밋·Pages)는 **`pages` 그룹**에 넣어 Add/Fix와 직렬화  
6. **`add-draw.yml` / `fix-draw.yml` 본문은 수정하지 말 것**

### 첫 운영 모드 제안

| 단계 | 기간 | apply | FCM |
|------|------|-------|-----|
| 0 (지금) | — | OFF | — |
| 1 | 1주 | ON (workflow_dispatch만) | OFF 또는 skip |
| 2 | 1주 | ON (cron) | ON |
| 3 | 안정 후 | ON 상시 | ON |

---

## 4. 하지 말 것

- `add-draw.yml` / `fix-draw.yml` 내용을 바꿔 “자동화에 맞춤”
- 검증 없이 cron apply를 바로 프로덕션 ON
- FCM에 당첨 번호·등수를 넣어 보내기 (계약: data-only `draw_data_ready`)
- Firebase JSON / 서비스 계정을 repo에 커밋
- apply 실패를 조용히 무시 (이슈/코멘트 필수)

---

## 5. 로또 위자드 앱은?

**대부분 수정 불필요.** 확인만 하면 된다.

자세한 체크·필요 시 Agent 프롬프트:

→ `C:\lotto_wizard\docs\ops\AUTO_DRAW_APPLY_APP_CHECK.md`

앱이 이미 하는 일:

1. 토픽 `draw_data` 구독  
2. `type=draw_data_ready` 수신 → Pages `manifest`/`draws_v3` sync  
3. 보관함 대조 → 로컬 알림  

자동 apply가 켜져도 **메시지는 Add와 동일**하므로, 앱은 “누가 올렸는지”를 구분할 필요가 없다.

앱 수정이 필요한 경우(예외):

- 알림 문구에 “자동 반영” 표기 등 UX 변경을 원할 때  
- sync URL / 스키마를 바꿀 때  
- iOS 등 다른 플랫폼 FCM을 새로 넣을 때  

---

## 6. 켜는 날 운영 절차 (한 장)

1. Cursor에서 `C:\lotto-data\auto-draw` (또는 repo 루트) 열고  
   [AGENT_PROMPT_APPLY.md](./AGENT_PROMPT_APPLY.md) 내용을 Agent에 붙여넣기  
2. PR 또는 main 반영 전: **기본 apply=false** 인지 코드 리뷰  
3. Actions → Auto draw → Run workflow  
   - draw_no = 이번 회차(또는 비움)  
   - apply = true (수동 1회 시험)  
   - once = true (이미 발표된 회차 디버그 시)  
4. 확인: `data: add draw N` 커밋 → Pages `latestDrawNo` → (FCM ON이면) 기기 알림  
5. 이슈 `[auto-draw] 실행 이력`에 성공/apply 결과 코멘트 확인  
6. 문제 없으면 다음 토요일 cron에 apply 기본 ON 검토  

실패 시 즉시:

- 번호 오탐 → **Fix lotto draw**  
- 미반영 → **Add lotto draw** (지금과 동일)  
- apply 플래그 OFF로 되돌리기  

---

## 7. 성공 판정

| 항목 | 기준 |
|------|------|
| 이력 | `FETCH_HISTORY.md`에 회차·번호 기록 |
| 데이터 | `manifest.latestDrawNo` = 해당 회차 |
| Pages | `draws_v3.json`에 동일 win6/bonus |
| FCM | (ON일 때) 종료 앱이 sync 후 알림 또는 로그 |
| 폴백 | Add/Fix 워크플로가 그대로 Run 가능 |

---

## Decision log (apply)

| 날짜 | 내용 |
|------|------|
| 2026-09-20 | 2~3주 fetch-only 후 apply 합의 |
| 2026-10-16 | 1243~1245 관찰 확인. APPLY_GUIDE / Agent 프롬프트 / 앱 체크 문서 작성 |
