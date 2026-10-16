# Cursor Agent 프롬프트 — Auto draw apply 연계

아래 블록을 **그대로** Cursor Agent 채팅에 붙여 넣으세요.  
워크스페이스는 `C:\lotto-data` (또는 `auto-draw` 폴더)를 권장합니다.

---

## 복사해서 쓸 프롬프트

```text
역할: lotto-data 의 Auto draw를 fetch-only에서 apply(엑셀→JSON→Pages→FCM)까지 연계하는 구현 Agent.

필수 문서 (먼저 읽고 따를 것):
- auto-draw/docs/APPLY_GUIDE.md
- auto-draw/docs/PLAN.md
- auto-draw/AGENTS.md
- .github/workflows/auto-draw.yml (현재 운용)
- .github/workflows/add-draw.yml (참고만 — 수정 금지)
- scripts/add_draw.py / scripts/send_fcm_draw_data.py (호출만)

절대 금지:
1) add-draw.yml / fix-draw.yml 내용 수정·삭제·비활성
2) Firebase 서비스 계정 JSON / google-services 를 repo에 커밋
3) 검증 없이 cron apply 기본값을 true 로 켜기
4) FCM에 당첨번호·등수 notification 페이로드 추가 (data-only draw_data_ready 유지)
5) 사용자 승인 없이 main 강제 push / 기존 수동 플로우 파괴

목표 동작:
1) 기존 auto-draw.yml 의 조회·relay·이력·이슈 로그는 유지
2) workflow_dispatch 입력 `apply` (boolean, 기본 false) 추가
3) schedule(cron)에서는 당분간 apply=false 고정. 나중에 사용자가 켤 수 있게 env/변수로만 분리해도 됨
4) steps.run.outputs.outcome == 'ready' 이고 numbers/bonus/draw_no 가 있을 때만 apply 후보
5) 이미 manifest.latestDrawNo >= draw_no 이면 apply skip (성공으로 처리, 중복 Add 방지)
6) manual_match == '불일치' 이면 apply 하지 말고 이슈에 경고 + Fix 안내
7) apply 성공 시 순서:
   - pip: openpyxl google-auth requests
   - python scripts/add_draw.py --draw-no … --numbers … --bonus … --repo-root . --version 3
   - git commit+push (메시지: data: add draw N) — Add와 동일 범위 파일
   - Pages: dist에 draws_v3.json + manifest.json → upload-pages-artifact → deploy-pages
   - FCM: scripts/send_fcm_draw_data.py --draw-no N --allow-missing-secret (secrets 사용)
8) concurrency: Pages/커밋 단계는 group: pages, cancel-in-progress: false (Add/Fix와 직렬)
9) fetch history 커밋과 apply 커밋이 충돌하지 않게 순서 정리 (이력 먼저 또는 apply 후 이력에 applied=true 기록 — 단순하고 race 적은 쪽 선택, 이유를 주석으로)
10) 이슈 "[auto-draw] 실행 이력"에 apply skip/success/fail 코멘트 추가
11) README.md / PLAN.md / APPLY_GUIDE.md Status 체크박스 갱신
12) 초안이 필요하면 auto-draw/workflows/ 에도 DRAFT 복사본 유지 가능. 프로덕션은 .github/workflows/auto-draw.yml 만 승격

구현 후 제출물:
- 변경 파일 목록과 한 줄 요약
- 수동 테스트 절차 (workflow_dispatch: once=true, apply=true, 이미 반영된 회차는 skip 되는지)
- Add/Fix 가 그대로 살아 있는지 확인 방법
- cron 기본 apply=false 인 증거 (yml 인용)

범위 밖:
- lotto_wizard 앱 코드 변경 (필요하면 C:\lotto_wizard\docs\ops\AUTO_DRAW_APPLY_APP_CHECK.md 만 확인 안내)
- Fix 자동화

시작: APPLY_GUIDE.md 와 현재 auto-draw.yml 을 읽고, 최소 diff 로 설계한 뒤 구현하라.
```

---

## 짧은 버전 (이미 문서를 읽은 채팅용)

```text
auto-draw에 apply 연계 구현해줘.
APPLY_GUIDE.md / AGENT_PROMPT_APPLY.md 전체 규칙을 따른다.
add-draw.yml·fix-draw.yml 수정 금지.
기본 apply=false, dispatch로만 시험 가능하게.
ready + 미반영 회차만 add_draw→Pages→FCM.
불일치면 apply 금지. PLAN/README 갱신.
```

---

## 검증 프롬프트 (구현 후 QA Agent)

```text
방금 넣은 Auto draw apply 변경을 리뷰해줘.
1) add-draw.yml / fix-draw.yml 이 diff에 포함됐으면 즉시 지적
2) cron 경로에서 apply가 기본 ON이면 차단 사유로 보고
3) 중복 apply(이미 latestDrawNo 반영) 방지 여부
4) pages concurrency / FCM data-only 계약 준수 여부
5) 수동 Add/Fix 폴백이 문서·이슈 문구에 남아 있는지
통과/실패와 수정 제안만 간결히.
```
